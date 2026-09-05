import { useEffect, useRef } from "react";
import { getDocument, GlobalWorkerOptions } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

GlobalWorkerOptions.workerSrc = workerUrl;

type Props = {
  documentName: string;
  page: number | null;
};

export function PdfEvidence({ documentName, page }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!documentName || !canvasRef.current) {
      return;
    }
    const canvas = canvasRef.current;
    const targetPage = page ?? 1;
    let cancelled = false;

    const render = async () => {
      const pdf = await getDocument(`/statements/${encodeURIComponent(documentName)}`).promise;
      if (cancelled) {
        return;
      }
      const pdfPage = await pdf.getPage(targetPage);
      const viewport = pdfPage.getViewport({ scale: 1.15 });
      const context = canvas.getContext("2d");
      if (!context) {
        return;
      }
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      await pdfPage.render({ canvasContext: context, viewport, canvas }).promise;
    };

    void render().catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [documentName, page]);

  if (!documentName) {
    return <p className="empty">No source PDF attached.</p>;
  }

  return (
    <div className="pdf-frame">
      <p className="pdf-caption">
        {documentName} · page {page ?? "?"}
      </p>
      <canvas ref={canvasRef} />
    </div>
  );
}
