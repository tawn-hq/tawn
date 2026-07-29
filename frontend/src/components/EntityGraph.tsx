import { useEffect, useRef } from 'react'
import cytoscape from 'cytoscape'
import fcose from 'cytoscape-fcose'
import type { GraphData } from '../lib/api'

// fcose is the force-directed layout that also handles compound clustering.
// Both it and cytoscape already ship as mermaid dependencies — promoting them
// to direct deps costs no new download, it just stops the build relying on a
// transitive hoist.
cytoscape.use(fcose)

const DOMAIN_COLOR: Record<string, string> = {
  work: '#9C5B33',
  wealth: '#3F8E62',
  research: '#8A63D2',
  academic: '#C2536B',
}

export default function EntityGraph({
  data,
  onSelect,
  height = 320,
}: {
  data: GraphData
  onSelect?: (label: string) => void
  height?: number
}) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current || data.nodes.length === 0) return

    const cy = cytoscape({
      container: ref.current,
      elements: [
        ...data.nodes.map((n) => ({
          data: { id: String(n.id), label: n.label, domain: n.domain || 'unassigned' },
        })),
        ...data.links.map((l, i) => ({
          data: {
            id: `e${i}`,
            source: String(l.source),
            target: String(l.target),
            label: l.relation,
            weight: l.weight,
          },
        })),
      ],
      style: [
        {
          selector: 'node',
          style: {
            'background-color': (el: cytoscape.NodeSingular) =>
              DOMAIN_COLOR[el.data('domain') as string] || '#948A76',
            label: 'data(label)',
            'font-size': 9,
            'font-family': 'JetBrains Mono, monospace',
            color: '#948A76',
            'text-valign': 'bottom',
            'text-margin-y': 4,
            width: 16,
            height: 16,
          },
        },
        {
          selector: 'edge',
          style: {
            // Weight is how often the pairing was seen — a one-off mention
            // should not look like a strong association.
            width: (el: cytoscape.EdgeSingular) =>
              Math.min(4, 1 + ((el.data('weight') as number) || 1) * 0.4),
            'line-color': '#D5CCB8',
            'curve-style': 'bezier',
            'target-arrow-shape': 'triangle',
            'target-arrow-color': '#D5CCB8',
            'arrow-scale': 0.7,
          },
        },
      ],
      layout: { name: 'fcose', animate: false, nodeSeparation: 90 } as cytoscape.LayoutOptions,
    })

    if (onSelect) {
      cy.on('tap', 'node', (evt) => onSelect(evt.target.data('label') as string))
    }
    return () => cy.destroy()
  }, [data, onSelect])

  if (data.nodes.length === 0) {
    return (
      <div
        style={{
          height,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 5,
          fontSize: 12,
          color: 'var(--tawn-text-3)',
          fontFamily: 'var(--tawn-font-mono)',
        }}
      >
        no links yet — run <code>tawn enrich</code>
      </div>
    )
  }
  return <div ref={ref} style={{ height, width: '100%' }} />
}
