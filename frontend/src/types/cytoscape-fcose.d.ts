// cytoscape-fcose ships no bundled types and has no @types package.
declare module 'cytoscape-fcose' {
  import type { Ext } from 'cytoscape'
  const ext: Ext
  export default ext
}
