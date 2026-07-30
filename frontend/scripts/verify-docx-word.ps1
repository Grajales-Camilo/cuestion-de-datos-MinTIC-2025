#Requires -Version 7.0
<#
.SYNOPSIS
    Verifica de forma reproducible que un .docx generado por F6-02B abre
    limpiamente en Microsoft Word real, sin depender de la propiedad
    `Document.Repaired` (no es evidencia soportada por el contrato público
    verificado de Word) y sin tocar ninguna instancia de Word que ya
    perteneciera al usuario.

.DESCRIPTION
    Contrato de uso:
        pwsh -File scripts/verify-docx-word.ps1 `
          -DocxPath "<ruta absoluta al archivo>" `
          -MinimumFootnotes 1

    Nunca imprime texto del documento, citas, tokens ni payloads: el resumen
    final solo contiene metadatos (hashes, conteos, booleanos, versión de
    Word).

.PARAMETER DocxPath
    Ruta (absoluta o relativa) al archivo .docx a verificar. Debe existir y
    no estar vacío.

.PARAMETER MinimumFootnotes
    Número mínimo de notas al pie (`Document.Footnotes.Count`) que el
    documento debe tener para considerarse una verificación exitosa.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$DocxPath,

    [Parameter(Mandatory = $true)]
    [int]$MinimumFootnotes
)

$ErrorActionPreference = "Stop"

# Códigos de salida (todos != 0 son fallo; el mensaje explica cuál).
$EXIT_OK = 0
$EXIT_INVALID_INPUT = 1
$EXIT_EXISTING_WORD_INSTANCE = 2
$EXIT_OPEN_FAILED = 3
$EXIT_FOOTNOTES_BELOW_MINIMUM = 4
$EXIT_FILE_CHANGED = 5
$EXIT_PROCESS_NOT_STOPPED = 6

# wdSaveOptions.wdDoNotSaveChanges — nunca se guardan cambios sobre el
# archivo verificado, sea cual sea el resultado.
$WD_DO_NOT_SAVE_CHANGES = 0

function Write-ClearError {
    param([string]$Message)
    Write-Error $Message -ErrorAction Continue
}

# 1) Resolver y comprobar que DocxPath es un archivo .docx existente y no vacío.
$resolvedPath = $null
try {
    $resolvedPath = (Resolve-Path -Path $DocxPath -ErrorAction Stop).Path
} catch {
    Write-ClearError "No se encontró el archivo indicado en -DocxPath: '$DocxPath'."
    exit $EXIT_INVALID_INPUT
}

$extension = [System.IO.Path]::GetExtension($resolvedPath)
if ($extension.ToLowerInvariant() -ne ".docx") {
    Write-ClearError "El archivo debe tener extensión .docx (recibido: '$extension')."
    exit $EXIT_INVALID_INPUT
}

$fileInfo = Get-Item -LiteralPath $resolvedPath
if ($fileInfo.Length -le 0) {
    Write-ClearError "El archivo '$resolvedPath' está vacío."
    exit $EXIT_INVALID_INPUT
}

# 2) SHA-256 ANTES de abrirlo.
$sha256Before = (Get-FileHash -LiteralPath $resolvedPath -Algorithm SHA256).Hash

# 3) Detectar procesos WINWORD preexistentes.
$pidsBefore = @(Get-Process -Name WINWORD -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)

# 4) Si ya hay una instancia de Word del usuario, negarse a continuar. Nunca
# se cierra ni se reutiliza un proceso ajeno.
if ($pidsBefore.Count -gt 0) {
    Write-ClearError (
        "Se detectó Word ya en ejecución (PID(s): $($pidsBefore -join ', ')). " +
        "Este script nunca cierra ni reutiliza instancias ajenas: cierra Word " +
        "manualmente y vuelve a ejecutar la verificación."
    )
    exit $EXIT_EXISTING_WORD_INSTANCE
}

$word = $null
$doc = $null
$opened = $false
$readOnly = $false
$footnotesCount = -1
$wordVersion = $null
$createdPid = $null
$createdProcessStopped = $false
$openError = $null

try {
    # 5) Instancia COM NUEVA de Word.
    $word = New-Object -ComObject Word.Application

    # 6) Configuración obligatoria.
    $word.Visible = $false
    $word.DisplayAlerts = 0 # wdAlertsNone: nunca un diálogo modal que bloquee la automatización.

    $wordVersion = $word.Version

    # Identificar el PID que esta ejecución realmente creó (nunca asumir que
    # es "el único" ni tocar ninguno preexistente).
    Start-Sleep -Milliseconds 500
    $pidsAfterCreate = @(Get-Process -Name WINWORD -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
    $newPids = @($pidsAfterCreate | Where-Object { $pidsBefore -notcontains $_ })
    if ($newPids.Count -gt 0) { $createdPid = $newPids[0] }

    # 7) Abrir el archivo: ReadOnly=true, AddToRecentFiles=false,
    # OpenAndRepair=false (posicional: la interfaz COM de Word no admite
    # argumentos con nombre desde PowerShell).
    $missing = [System.Reflection.Missing]::Value
    $doc = $word.Documents.Open(
        $resolvedPath,  # FileName
        $missing,       # ConfirmConversions
        $true,          # ReadOnly
        $false,         # AddToRecentFiles
        $missing,       # PasswordDocument
        $missing,       # PasswordTemplate
        $missing,       # Revert
        $missing,       # WritePasswordDocument
        $missing,       # WritePasswordTemplate
        $missing,       # Format
        $missing,       # Encoding
        $missing,       # Visible
        $false          # OpenAndRepair
    )

    if ($null -eq $doc) {
        throw "Documents.Open no devolvió un documento."
    }

    # 8) Éxito de apertura: el documento existe, sigue abierto, y no hubo
    # excepción COM hasta aquí. `Document.Repaired` NO se consulta (9): no
    # es evidencia soportada por el contrato público verificado.
    $opened = $true
    $readOnly = [bool]$doc.ReadOnly
    $footnotesCount = [int]$doc.Footnotes.Count
} catch {
    $openError = $_.Exception.Message
} finally {
    # 10) Cerrar el documento sin guardar cambios.
    if ($null -ne $doc) {
        try { $doc.Close($WD_DO_NOT_SAVE_CHANGES) } catch {}
    }
    # 11) Cerrar SOLO la instancia creada por este script.
    if ($null -ne $word) {
        if ($null -ne $createdPid) {
            try { $word.Quit() } catch {}
        }
        # Si nunca se detectó un PID nuevo propio, no se llama Quit(): no
        # hay evidencia de haber creado una instancia separada y llamar
        # Quit() arriesgaría cerrar una instancia ajena.
    }
    # 12) Liberar objetos COM.
    if ($null -ne $doc) { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($doc) | Out-Null }
    if ($null -ne $word) { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null }
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
}

# 13) Verificar que el PID creado terminó (con margen: Quit() es asíncrono).
if ($null -ne $createdPid) {
    $deadline = (Get-Date).AddSeconds(10)
    while ((Get-Date) -lt $deadline) {
        if (-not (Get-Process -Id $createdPid -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 300
    }
    $stillRunning = Get-Process -Id $createdPid -ErrorAction SilentlyContinue
    if ($stillRunning) {
        # Confirmado por PID-diff: es la instancia creada por este script,
        # nunca una ajena. Se termina explícitamente tras agotar el margen.
        try { Stop-Process -Id $createdPid -Force -ErrorAction Stop } catch {}
        Start-Sleep -Milliseconds 300
        $stillRunning = Get-Process -Id $createdPid -ErrorAction SilentlyContinue
    }
    $createdProcessStopped = -not [bool]$stillRunning
} else {
    # No se detectó un PID nuevo: no hay proceso propio que verificar como
    # detenido. Se marca como cumplido vacuamente (nada que dejar corriendo).
    $createdProcessStopped = $true
}

# 14) SHA-256 DESPUÉS y confirmación de que el archivo no cambió.
$sha256After = (Get-FileHash -LiteralPath $resolvedPath -Algorithm SHA256).Hash
$fileUnchanged = ($sha256Before -eq $sha256After)

$footnotesOk = $opened -and ($footnotesCount -ge $MinimumFootnotes)

# 15) Exit code 0 solo si TODAS las comprobaciones pasan.
$allChecksPassed = $opened -and $readOnly -and $footnotesOk -and $fileUnchanged -and $createdProcessStopped

# 16) Resumen JSON seguro (17: nunca texto del documento, citas, tokens ni payloads).
$summary = [ordered]@{
    opened                = $opened
    readOnly              = $readOnly
    footnotesCount        = $footnotesCount
    minimumFootnotes      = $MinimumFootnotes
    sha256Before           = $sha256Before
    sha256After            = $sha256After
    fileUnchanged          = $fileUnchanged
    wordVersion            = $wordVersion
    createdProcessStopped  = $createdProcessStopped
    allChecksPassed        = $allChecksPassed
}
if ($openError) { $summary["openError"] = $openError }

$summary | ConvertTo-Json -Compress | Write-Output

if (-not $opened) { exit $EXIT_OPEN_FAILED }
if (-not $footnotesOk) { exit $EXIT_FOOTNOTES_BELOW_MINIMUM }
if (-not $fileUnchanged) { exit $EXIT_FILE_CHANGED }
if (-not $createdProcessStopped) { exit $EXIT_PROCESS_NOT_STOPPED }
exit $EXIT_OK
