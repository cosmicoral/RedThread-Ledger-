import { useEffect, useRef, useState } from "react";
import { getDocument, GlobalWorkerOptions } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { apiUrl } from "../api";

GlobalWorkerOptions.workerSrc = workerUrl;

type Props = {
  documentName: string;
  page: number | null;
};

export function PdfEvidence({ documentName, page }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    if (!documentName) {
      return;
    }
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }
    const targetPage = page ?? 1;
    let cancelled = false;
    setState("loading");

    const render = async () => {
      const pdf = await getDocument(apiUrl(`/statements/${encodeURIComponent(documentName)}`)).promise;
      if (cancelled) {
        return;
      }
      const pdfPage = await pdf.getPage(targetPage);
      const viewport = pdfPage.getViewport({ scale: 1.15 });
      const context = canvas.getContext("2d");
      if (!context) {
        throw new Error("canvas");
      }
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      await pdfPage.render({ canvasContext: context, viewport, canvas }).promise;
      if (!cancelled) {
        setState("ready");
      }
    };

    void render().catch(() => {
      if (!cancelled) {
        setState("error");
      }
    });
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
        Source citation: {documentName} · page {page ?? "?"}
      </p>
      {state === "loading" ? <p className="empty">Loading PDF page…</p> : null}
      {state === "error" ? (
        <p className="empty">
          Could not render the PDF page.{" "}
          <a href={apiUrl(`/statements/${encodeURIComponent(documentName)}`)} target="_blank" rel="noreferrer">
            Open the source document
          </a>
        </p>
      ) : null}
      <canvas ref={canvasRef} hidden={state !== "ready"} />
      {state !== "ready" ? (
        <iframe
          title="Source statement"
          src={`${apiUrl(`/statements/${encodeURIComponent(documentName)}`)}#page=${page ?? 1}`}
        />
      ) : null}
    </div>
  );
}
