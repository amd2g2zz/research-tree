/** Markdown + KaTeX + 语法高亮渲染管线（#718/#723）。
 *
 * marked + marked-highlight（highlight.js 代码块着色）+ marked-katex-extension
 * （$...$ 行内 / $$...$$ 块级）+ KaTeX 输出，DOMPurify sanitize（katex 的
 * class/style 默认保留，trust=false 禁止 \href 任意跳转）。 */
import DOMPurify from "dompurify";
import hljs from "highlight.js";
import "highlight.js/styles/github.css";
import { marked } from "marked";
import { markedHighlight } from "marked-highlight";
import markedKatex from "marked-katex-extension";

let configured = false;

function ensureConfigured(): void {
	if (configured) return;
	marked.use(
		markedHighlight({
			langPrefix: "hljs language-",
			highlight(code: string, lang: string) {
				const l =
					lang !== "" && hljs.getLanguage(lang) !== undefined
						? lang
						: "plaintext";
				return hljs.highlight(code, { language: l }).value;
			},
		}),
	);
	marked.use(markedKatex({ nonStandard: false }));
	configured = true;
}

export function renderMd(text: string): string {
	ensureConfigured();
	const html = marked.parse(text ?? "", { async: false }) as string;
	return DOMPurify.sanitize(html, {
		USE_PROFILES: { html: true, mathMl: true, svg: true },
	});
}
