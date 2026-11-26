import Markdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

export function AssistantMarkdown({ children }: { children: string }) {
  return (
    <div className="min-w-0 [overflow-wrap:anywhere] [&_.katex-display]:overflow-x-auto">
      <Markdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          pre: ({ node: _node, ...props }) => (
            <pre {...props} tabIndex={0} className="max-w-full overflow-x-auto whitespace-pre" />
          ),
          table: ({ node: _node, ...props }) => (
            <div
              className="max-w-full overflow-x-auto"
              tabIndex={0}
              role="region"
              aria-label="Bảng kết quả"
            >
              <table {...props} className="[overflow-wrap:normal]" />
            </div>
          ),
        }}
      >
        {children}
      </Markdown>
    </div>
  );
}
