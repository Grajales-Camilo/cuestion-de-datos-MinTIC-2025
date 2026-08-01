import {
  Document,
  ExternalHyperlink,
  HeadingLevel,
  ImageRun,
  LevelFormat,
  Packer,
  Paragraph,
  Table,
  TableCell,
  TableRow,
  TextRun,
} from "docx";
import JSZip from "jszip";

export function bufferToArrayBuffer(buffer) {
  const arrayBuffer = new ArrayBuffer(buffer.byteLength);
  new Uint8Array(arrayBuffer).set(buffer);
  return arrayBuffer;
}

/** Fixture sintético y versionable: no proviene de documentos reales ni
 * contiene información personal. */
export async function createRichSyntheticDocx({
  link = "https://example.test/recurso",
  includeTable = false,
  includeImage = false,
} = {}) {
  const children = [
    new Paragraph({ text: "Título sintético", heading: HeadingLevel.HEADING_1 }),
    new Paragraph({
      children: [
        new TextRun("Párrafo "),
        new TextRun({ text: "negrita", bold: true }),
        new TextRun(" y "),
        new TextRun({ text: "cursiva", italics: true }),
        new TextRun(" con "),
        new ExternalHyperlink({
          children: [new TextRun({ text: "enlace", style: "Hyperlink" })],
          link,
        }),
      ],
    }),
    new Paragraph({ text: "Elemento con viñeta", bullet: { level: 0 } }),
    new Paragraph({ text: "Elemento numerado", numbering: { reference: "synthetic-numbering", level: 0 } }),
  ];
  if (includeTable) {
    children.push(
      new Table({
        rows: [
          new TableRow({
            children: [
              new TableCell({ children: [new Paragraph("Celda A")] }),
              new TableCell({ children: [new Paragraph("Celda B")] }),
            ],
          }),
        ],
      }),
    );
  }
  if (includeImage) {
    // PNG sintético de 1×1 px creado de bytes constantes, no de un recurso
    // real ni descargado. Permite ejercer el descarte de imágenes referidas.
    children.push(new Paragraph({
      children: [new ImageRun({
        type: "png",
        data: Buffer.from(
          "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
          "base64",
        ),
        transformation: { width: 1, height: 1 },
      })],
    }));
  }

  const document = new Document({
    numbering: {
      config: [
        {
          reference: "synthetic-numbering",
          levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1." }],
        },
      ],
    },
    sections: [{ children }],
  });
  return Packer.toBuffer(document);
}

export async function mutateSyntheticDocx(buffer, mutate) {
  const zip = await JSZip.loadAsync(buffer);
  await mutate(zip);
  return zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" });
}

export async function addExternalRelationship(buffer) {
  return mutateSyntheticDocx(buffer, async (zip) => {
    const path = "word/_rels/document.xml.rels";
    const xml = await zip.file(path).async("string");
    zip.file(
      path,
      xml.replace(
        "</Relationships>",
        '<Relationship Id="rExternal" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/attachedTemplate" Target="https://example.test/template.dotx" TargetMode="External"/></Relationships>',
      ),
    );
  });
}

export async function addUnsupportedSyntheticParts(buffer) {
  return mutateSyntheticDocx(buffer, async (zip) => {
    zip.file("word/header1.xml", "<w:hdr/>");
    zip.file("word/footer1.xml", "<w:ftr/>");
    zip.file(
      "word/comments.xml",
      '<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:comment w:id="1"><w:p><w:r><w:t>Comentario sintético</w:t></w:r></w:p></w:comment></w:comments>',
    );
    zip.file(
      "word/footnotes.xml",
      '<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:footnote w:id="1"><w:p><w:r><w:t>Nota sintética</w:t></w:r></w:p></w:footnote></w:footnotes>',
    );
    zip.file(
      "word/endnotes.xml",
      '<w:endnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:endnote w:id="1"><w:p><w:r><w:t>Nota final sintética</w:t></w:r></w:p></w:endnote></w:endnotes>',
    );
    zip.file("word/embeddings/object1.bin", new Uint8Array([1, 2, 3]));
    const path = "word/document.xml";
    const xml = await zip.file(path).async("string");
    zip.file(
      path,
      xml.replace(
        "</w:body>",
        '<w:p><w:commentRangeStart w:id="1"/><w:r><w:t>Texto comentado</w:t></w:r><w:commentRangeEnd w:id="1"/><w:r><w:commentReference w:id="1"/></w:r><w:r><w:footnoteReference w:id="1"/><w:endnoteReference w:id="1"/></w:r><w:ins><w:r><w:t>Cambio sintético</w:t></w:r></w:ins><w:fldSimple w:instr="DATE"><w:r><w:t>Campo</w:t></w:r></w:fldSimple><m:oMath/></w:p></w:body>',
      ),
    );
  });
}
