/**
 * Narrativa propia de `evidence.narrative`. Renderiza con React (nunca
 * `dangerouslySetInnerHTML`), resaltando únicamente coincidencias literales
 * de `claims[].display_value` — no recalcula, redondea ni reformatea
 * ninguna cifra (Art. I). Cada valor resaltado queda relacionado
 * accesiblemente con su claim vía `aria-label` del `<mark>`. Sin narrativa,
 * no inventa una.
 */
function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function EvidenceNarrative({ narrative, claims }) {
  if (typeof narrative !== "string" || narrative.trim() === "") return null;

  const valueToClaim = new Map();
  for (const claim of Array.isArray(claims) ? claims : []) {
    const value = typeof claim?.display_value === "string" ? claim.display_value : null;
    if (!value || value.trim() === "" || valueToClaim.has(value)) continue;
    valueToClaim.set(value, claim);
  }

  const values = [...valueToClaim.keys()].sort((a, b) => b.length - a.length);
  if (values.length === 0) {
    return <p className="text-cdt-sm text-cdt-slate-900">{narrative}</p>;
  }

  const pattern = new RegExp(`(${values.map(escapeRegExp).join("|")})`, "g");
  const parts = narrative.split(pattern);

  return (
    <p className="text-cdt-sm text-cdt-slate-900">
      {parts.map((part, index) => {
        const claim = valueToClaim.get(part);
        if (!claim) return <span key={index}>{part}</span>;
        const label =
          claim.label_status === "verified" && typeof claim.label === "string" && claim.label.trim() !== ""
            ? claim.label
            : null;
        return (
          <mark key={index} className="rounded-cdt-sm bg-cdt-blue-100 px-0.5" aria-label={label ? `${part}, ${label}` : part}>
            {part}
          </mark>
        );
      })}
    </p>
  );
}
