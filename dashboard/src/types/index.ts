export interface BandwidthPoint {
  time: string
  bytes: number
}

export interface TopTalker {
  src_ip: string
  value: number
}

export interface ProtocolData {
  protocol: string
  bytes: number
}

export interface Alert {
  rule_name: string
  severity: 'info' | 'warning' | 'critical'
  message: string
  flow_data: Record<string, any>
  timestamp: string
  acknowledged: boolean
}

export interface FlowRecord {
  src_ip: string
  dst_ip: string
  src_port: number
  dst_port: number
  protocol: number
  bytes: number
  packets: number
  start_time: number
  end_time: number
}

export interface TopTalkersResponse {
  talkers: TopTalker[]
}

export interface BandwidthResponse {
  series: BandwidthPoint[]
}

export interface ProtocolDistributionResponse {
  distribution: ProtocolData[]
}

export interface SummaryResponse {
  time_range: { start: string; stop: string }
  total_bytes: number
  total_flows_estimate: number
  top_talkers: TopTalker[]
  protocol_distribution: ProtocolData[]
  bandwidth_series: BandwidthPoint[]
}