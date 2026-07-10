import { ReactNode } from "react";

type TableBlock = {
  header: string[];
  rows: string[][];
};

function parseInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    const token = match[0];
    if (token.startsWith("`")) {
      nodes.push(
        <code
          key={`${match.index}-code`}
          className="rounded-md bg-[#eaf0ec] px-1.5 py-0.5 font-mono text-[0.92em] text-[#244535]"
        >
          {token.slice(1, -1)}
        </code>,
      );
    } else {
      nodes.push(
        <strong key={`${match.index}-strong`} className="font-semibold text-[#20372b]">
          {token.slice(2, -2)}
        </strong>,
      );
    }
    lastIndex = match.index + token.length;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes;
}

function isRule(line: string) {
  return /^-{3,}$/.test(line.trim());
}

function isHeading(line: string) {
  return /^#{1,4}\s+/.test(line);
}

function isUnorderedItem(line: string) {
  return /^\s*[-*]\s+/.test(line);
}

function isOrderedItem(line: string) {
  return /^\s*\d+[.)]\s+/.test(line);
}

function isTableSeparator(line: string) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

function splitTableRow(line: string) {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function readTable(lines: string[], start: number): { table: TableBlock; next: number } {
  const header = splitTableRow(lines[start]);
  let index = start + 2;
  const rows: string[][] = [];
  while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
    rows.push(splitTableRow(lines[index]));
    index += 1;
  }
  return { table: { header, rows }, next: index };
}

function renderTable(table: TableBlock, key: number) {
  return (
    <div key={key} className="my-4 max-w-full overflow-x-auto rounded-2xl border border-[#dfe8e2] bg-white">
      <table className="w-full border-collapse text-left text-sm">
        <thead className="bg-[#f0f6ed] text-[#263b30]">
          <tr>
            {table.header.map((cell, index) => (
              <th key={`${cell}-${index}`} className="px-4 py-3 font-semibold">
                {parseInline(cell)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, rowIndex) => (
            <tr key={rowIndex} className="border-t border-[#e4ebe6]">
              {table.header.map((_, cellIndex) => (
                <td key={cellIndex} className="px-4 py-3 align-top text-[#4d5f55]">
                  {parseInline(row[cellIndex] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderHeading(
  level: number,
  content: ReactNode[],
  className: string,
  key: number,
) {
  if (level === 1) {
    return (
      <h2 key={key} className={className}>
        {content}
      </h2>
    );
  }
  if (level === 2) {
    return (
      <h3 key={key} className={className}>
        {content}
      </h3>
    );
  }
  return (
    <h4 key={key} className={className}>
      {content}
    </h4>
  );
}

export function MarkdownText({
  text,
  className = "",
}: {
  text: string;
  className?: string;
}) {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    if (
      line.includes("|") &&
      index + 1 < lines.length &&
      isTableSeparator(lines[index + 1])
    ) {
      const { table, next } = readTable(lines, index);
      blocks.push(renderTable(table, index));
      index = next;
      continue;
    }

    if (isRule(line)) {
      blocks.push(<hr key={index} className="my-5 border-[#dfe7e2]" />);
      index += 1;
      continue;
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      const content = parseInline(heading[2]);
      const headingClass =
        level === 1
          ? "mt-1 text-xl font-semibold tracking-[-0.02em] text-[#20372b]"
          : level === 2
            ? "mt-5 text-lg font-semibold text-[#20372b]"
            : "mt-4 text-base font-semibold text-[#263b30]";
      blocks.push(renderHeading(level, content, headingClass, index));
      index += 1;
      continue;
    }

    if (isUnorderedItem(line) || isOrderedItem(line)) {
      const ordered = isOrderedItem(line);
      const items: string[] = [];
      while (
        index < lines.length &&
        (ordered ? isOrderedItem(lines[index]) : isUnorderedItem(lines[index]))
      ) {
        items.push(
          lines[index].replace(ordered ? /^\s*\d+[.)]\s+/ : /^\s*[-*]\s+/, ""),
        );
        index += 1;
      }
      const ListTag = ordered ? "ol" : "ul";
      blocks.push(
        <ListTag
          key={index}
          className={`my-3 space-y-1 pl-5 text-sm leading-7 text-[#405149] ${
            ordered ? "list-decimal" : "list-disc"
          }`}
        >
          {items.map((item, itemIndex) => (
            <li key={`${item}-${itemIndex}`}>{parseInline(item)}</li>
          ))}
        </ListTag>,
      );
      continue;
    }

    const paragraphLines = [line.trim()];
    index += 1;
    while (
      index < lines.length &&
      lines[index].trim() &&
      !isHeading(lines[index]) &&
      !isRule(lines[index]) &&
      !isUnorderedItem(lines[index]) &&
      !isOrderedItem(lines[index]) &&
      !(lines[index].includes("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1]))
    ) {
      paragraphLines.push(lines[index].trim());
      index += 1;
    }
    blocks.push(
      <p key={index} className="my-3 text-sm leading-7 text-[#405149]">
        {parseInline(paragraphLines.join(" "))}
      </p>,
    );
  }

  return (
    <div className={`min-w-0 max-w-full break-words [overflow-wrap:anywhere] ${className}`}>
      {blocks}
    </div>
  );
}
