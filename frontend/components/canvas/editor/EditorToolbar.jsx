import {
  Bold,
  Heading2,
  Heading3,
  Heading4,
  Italic,
  List,
  ListOrdered,
  Quote,
} from "lucide-react";
import { IconButton } from "../../ui/IconButton";

function FormatButton({ label, pressed, onClick, children, disabled }) {
  return (
    <IconButton
      label={label}
      variant={pressed ? "secondary" : "quiet"}
      aria-pressed={pressed}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </IconButton>
  );
}

/** Barra cerrada de formatos permitidos por el esquema F5-01. */
export function EditorToolbar({ editor }) {
  const disabled = !editor;
  const run = (command) => {
    if (!editor) return;
    command(editor.chain().focus()).run();
  };

  return (
    <div
      role="toolbar"
      aria-label="Formato del documento"
      className="flex flex-wrap items-center gap-cdt-1 border-b border-cdt-blue-100 bg-cdt-blue-50 p-cdt-2"
    >
      <FormatButton
        label="Encabezado nivel 2"
        pressed={editor?.isActive("heading", { level: 2 }) ?? false}
        onClick={() => run((chain) => chain.toggleHeading({ level: 2 }))}
        disabled={disabled}
      >
        <Heading2 className="h-5 w-5" />
      </FormatButton>
      <FormatButton
        label="Encabezado nivel 3"
        pressed={editor?.isActive("heading", { level: 3 }) ?? false}
        onClick={() => run((chain) => chain.toggleHeading({ level: 3 }))}
        disabled={disabled}
      >
        <Heading3 className="h-5 w-5" />
      </FormatButton>
      <FormatButton
        label="Encabezado nivel 4"
        pressed={editor?.isActive("heading", { level: 4 }) ?? false}
        onClick={() => run((chain) => chain.toggleHeading({ level: 4 }))}
        disabled={disabled}
      >
        <Heading4 className="h-5 w-5" />
      </FormatButton>
      <FormatButton
        label="Negrita"
        pressed={editor?.isActive("bold") ?? false}
        onClick={() => run((chain) => chain.toggleBold())}
        disabled={disabled}
      >
        <Bold className="h-5 w-5" />
      </FormatButton>
      <FormatButton
        label="Cursiva"
        pressed={editor?.isActive("italic") ?? false}
        onClick={() => run((chain) => chain.toggleItalic())}
        disabled={disabled}
      >
        <Italic className="h-5 w-5" />
      </FormatButton>
      <FormatButton
        label="Lista con viñetas"
        pressed={editor?.isActive("bulletList") ?? false}
        onClick={() => run((chain) => chain.toggleBulletList())}
        disabled={disabled}
      >
        <List className="h-5 w-5" />
      </FormatButton>
      <FormatButton
        label="Lista numerada"
        pressed={editor?.isActive("orderedList") ?? false}
        onClick={() => run((chain) => chain.toggleOrderedList())}
        disabled={disabled}
      >
        <ListOrdered className="h-5 w-5" />
      </FormatButton>
      <FormatButton
        label="Cita en bloque"
        pressed={editor?.isActive("blockquote") ?? false}
        onClick={() => run((chain) => chain.toggleBlockquote())}
        disabled={disabled}
      >
        <Quote className="h-5 w-5" />
      </FormatButton>
    </div>
  );
}
