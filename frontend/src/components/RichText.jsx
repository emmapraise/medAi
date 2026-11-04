import { Fragment } from "react";

const INLINE = /((?:\[\d+\]\s*)+)|\*\*(.+?)\*\*/g;
const BULLET = /^\s*(?:[-*•]|\d+[.)])\s+/;

// A "[2]" marker becomes a button only once its source is known (citations arrive after the text).
function Cite({ n, cites, onCite }) {
  const cite = cites.find((c) => c.n === n);
  if (!cite) return <>[{n}]</>;
  return (
    <button type="button" className="cite" onClick={() => onCite(n)} aria-label={`Source ${n}: ${cite.source}, ${cite.question}`}>
      {n}
    </button>
  );
}

function inline(text, cites, onCite) {
  const out = [];
  let last = 0;
  let m;
  INLINE.lastIndex = 0;
  while ((m = INLINE.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[2] !== undefined) out.push(<strong key={m.index}>{m[2]}</strong>);
    else m[1].match(/\d+/g).forEach((n, i) => out.push(<Cite key={`${m.index}-${i}`} n={Number(n)} cites={cites} onCite={onCite} />));
    last = INLINE.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

/** Just enough markdown for model answers: paragraphs, bullet/numbered lists, **bold**, and [n] citation chips. */
export default function RichText({ text, cites = [], onCite = () => {} }) {
  return text
    .trim()
    .split(/\n{2,}/)
    .map((block, i) => {
      const lines = block.split("\n");
      if (lines.every((l) => BULLET.test(l))) {
        const ordered = /^\s*\d/.test(lines[0]);
        const Tag = ordered ? "ol" : "ul";
        return (
          <Tag key={i} start={ordered ? parseInt(lines[0].trim(), 10) : undefined}>
            {lines.map((l, j) => <li key={j}>{inline(l.replace(BULLET, ""), cites, onCite)}</li>)}
          </Tag>
        );
      }
      return (
        <p key={i}>
          {lines.map((l, j) => <Fragment key={j}>{j > 0 && <br />}{inline(l, cites, onCite)}</Fragment>)}
        </p>
      );
    });
}
