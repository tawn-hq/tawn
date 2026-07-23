/**
 * Renders fenced ```mermaid and ```dot/```graphviz code blocks left behind
 * by `marked` into inline SVG diagrams. Call after setting markdown-derived
 * innerHTML on a container; blocks that fail to render (bad syntax) are
 * left as plain code so nothing silently disappears.
 */

let mermaidPromise: Promise<typeof import('mermaid').default> | null = null

async function getMermaid() {
  if (!mermaidPromise) {
    mermaidPromise = import('mermaid').then((mod) => {
      const isDark = document.documentElement.getAttribute('data-theme') === 'dark'
        || (document.documentElement.getAttribute('data-theme') !== 'light'
          && window.matchMedia('(prefers-color-scheme: dark)').matches)
      mod.default.initialize({ startOnLoad: false, securityLevel: 'strict', theme: isDark ? 'dark' : 'default' })
      return mod.default
    })
  }
  return mermaidPromise
}

let graphvizPromise: Promise<import('@hpcc-js/wasm-graphviz').Graphviz> | null = null

async function getGraphviz() {
  if (!graphvizPromise) {
    graphvizPromise = import('@hpcc-js/wasm-graphviz').then((mod) => mod.Graphviz.load())
  }
  return graphvizPromise
}

let seq = 0

function wrapSvg(svg: string): HTMLDivElement {
  const wrapper = document.createElement('div')
  wrapper.className = 'tawn-diagram'
  wrapper.style.cssText = 'margin:10px 0;overflow-x:auto;background:var(--tawn-raised);border:1px solid var(--tawn-line);border-radius:8px;padding:12px;'
  wrapper.innerHTML = svg
  const svgEl = wrapper.querySelector('svg')
  if (svgEl) {
    svgEl.style.maxWidth = '100%'
    svgEl.style.height = 'auto'
  }
  return wrapper
}

export async function renderDiagramsIn(container: HTMLElement): Promise<void> {
  const mermaidBlocks = Array.from(container.querySelectorAll('pre > code.language-mermaid'))
  const dotBlocks = Array.from(container.querySelectorAll('pre > code.language-dot, pre > code.language-graphviz'))
  if (mermaidBlocks.length === 0 && dotBlocks.length === 0) return

  await Promise.all([
    ...mermaidBlocks.map(async (block) => {
      const code = block.textContent || ''
      const pre = block.closest('pre')
      if (!pre || !code.trim()) return
      try {
        const mermaid = await getMermaid()
        const id = `tawn-mermaid-${Date.now()}-${seq++}`
        const { svg } = await mermaid.render(id, code)
        pre.replaceWith(wrapSvg(svg))
      } catch {
        // leave the original code block in place on parse/render failure
      }
    }),
    ...dotBlocks.map(async (block) => {
      const code = block.textContent || ''
      const pre = block.closest('pre')
      if (!pre || !code.trim()) return
      try {
        const graphviz = await getGraphviz()
        const svg = graphviz.layout(code, 'svg', 'dot')
        pre.replaceWith(wrapSvg(svg))
      } catch {
        // leave the original code block in place on parse/render failure
      }
    }),
  ])
}
