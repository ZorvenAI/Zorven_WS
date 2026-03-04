'use client';

import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { ClipboardCopy, Check } from 'lucide-react';

interface MarkdownMessageProps {
  content: string;
}

function CodeBlock({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  const [copied, setCopied] = useState(false);
  const text = String(children).replace(/\n$/, '');
  const language = className?.replace('hljs language-', '')?.replace('language-', '') || '';

  const handleCopy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="group relative my-3 rounded-lg overflow-hidden bg-black/30 border border-white/5">
      <div className="flex items-center justify-between px-3 py-1.5 bg-white/5 border-b border-white/5">
        <span className="text-[10px] text-brand-silver/40 uppercase tracking-wider">
          {language || 'code'}
        </span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-[10px] text-brand-silver/40 hover:text-brand-silver transition-colors"
        >
          {copied ? (
            <>
              <Check className="w-3 h-3" />
              Copied
            </>
          ) : (
            <>
              <ClipboardCopy className="w-3 h-3" />
              Copy
            </>
          )}
        </button>
      </div>
      <pre className="overflow-x-auto p-3 text-sm leading-relaxed">
        <code className={className}>{children}</code>
      </pre>
    </div>
  );
}

export function MarkdownMessage({ content }: MarkdownMessageProps) {
  return (
    <div className="prose-chat">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          h1: ({ children }) => (
            <h1 className="font-heading text-lg font-heading font-bold text-white mt-4 mb-2">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="font-heading text-base font-heading font-bold text-white mt-3 mb-1.5">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="font-heading text-sm font-heading font-semibold text-white mt-2 mb-1">
              {children}
            </h3>
          ),
          p: ({ children }) => (
            <p className="text-sm leading-relaxed mb-2 last:mb-0">
              {children}
            </p>
          ),
          ul: ({ children }) => (
            <ul className="text-sm list-disc list-outside space-y-1 mb-2 ml-5">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="text-sm list-decimal list-outside space-y-1 mb-2 ml-5">
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li className="text-sm leading-relaxed">{children}</li>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-brand-electric/40 pl-3 my-2 text-brand-silver/70 italic text-sm">
              {children}
            </blockquote>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-brand-electric hover:underline"
            >
              {children}
            </a>
          ),
          strong: ({ children }) => (
            <strong className="font-semibold text-white">{children}</strong>
          ),
          em: ({ children }) => (
            <em className="italic text-brand-silver/80">{children}</em>
          ),
          code: ({ className, children, ...props }) => {
            // Inline code vs code block
            const isBlock = className?.includes('language-') || className?.includes('hljs');
            if (isBlock) {
              return (
                <CodeBlock className={className}>{children}</CodeBlock>
              );
            }
            return (
              <code
                className="px-1.5 py-0.5 rounded bg-white/10 text-brand-electric text-xs font-mono"
                {...props}
              >
                {children}
              </code>
            );
          },
          pre: ({ children }) => {
            // The <pre> wraps <code> for code blocks. We handle styling in the
            // code component's CodeBlock, so just pass children through here.
            return <>{children}</>;
          },
          table: ({ children }) => (
            <div className="overflow-x-auto my-2">
              <table className="text-xs border-collapse w-full">
                {children}
              </table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border border-white/10 px-2 py-1 bg-white/5 text-left font-semibold text-white">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-white/10 px-2 py-1 text-brand-silver">
              {children}
            </td>
          ),
          hr: () => <hr className="border-white/10 my-3" />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
