export interface Episode {
  id:string; session_id:string; source_ref:string; recorded_at:string; summary:string; excerpt?:string
  revision:number; pinned:number; truncated:number; kind:'event'|'impression'; valid_from:string
  valid_until:string|null; corrected_at:string|null; effective_status:'active'|'expired'|'future'
  history?:Episode[]; aliases?:string[]; match_kind?:string; matched_terms?:string[]
}
export interface MemoryStar {
  id:string; revision:number; recorded_at:string; summary:string; pinned:boolean; kind:'event'|'impression'
  valid_from:string; valid_until:string|null; corrected_at:string|null
  effective_status:'active'|'expired'|'future'; aliases:string[]; group:string
}
export interface MemoryEdge {source:string;target:string;reasons:{kind:'conversation'|'alias';label:string}[]}
export interface MemoryGraphData {
  revision:string; generated_at:string; nodes:MemoryStar[]; edges:MemoryEdge[]
  stats:{current:number;historical:number;matched:number;shown:number;omitted:number;pinned:number;node_limit:number;edge_limit:number;omitted_edges:number}
  range:{from:string|null;to:string|null}; semantics:string
}
