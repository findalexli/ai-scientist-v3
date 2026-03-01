import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";

import { Button } from "~/components/ui/button";

interface Props {
  url: string;
}

/**
 * PDF viewer using an iframe with PDF.js.
 * Falls back to a simple download link if iframe loading fails.
 */
export function PdfViewer({ url }: Props) {
  const [error, setError] = useState(false);

  if (error) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <p className="mb-2">Unable to display PDF inline.</p>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm underline"
        >
          Download PDF
        </a>
      </div>
    );
  }

  return (
    <div className="border rounded-lg overflow-hidden">
      <iframe
        src={url}
        className="w-full"
        style={{ height: "70vh", minHeight: "500px" }}
        title="Paper PDF"
        onError={() => setError(true)}
      />
    </div>
  );
}
