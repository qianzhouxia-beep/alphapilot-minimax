import { useEffect, useState } from "react"

type Data = {
  icir_top: { factor: string; ic_mean: number; abs_icir: number }[]
  long_auc: number
  short_auc: number
  oos: { n_trades: number; total_return_pct: number; sharpe: number; max_dd_pct: number; win_rate_pct: number; profit_factor: number }
  signal: { action: string; direction: string; confidence: number; price: number; symbol: string }[]
}

const COLORS = {
  bg: "#0f172a",
  card: "#1e293b",
  border: "#334155",
  green: "#22c55e",
  red: "#ef4444",
  amber: "#f59e0b",
  blue: "#3b82f6",
  text: "#f1f5f9",
  muted: "#94a3b8",
}

function Bar({ label, value, max, color, invert }: { label: string; value: number; max: number; color: string; invert?: boolean }) {
  const pct = Math.abs(value) / max * 100
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
      <span style={{ width: 130, fontSize: 11, color: COLORS.muted, textAlign: "right", flexShrink: 0 }}>{label}</span>
      <div style={{ flex: 1, height: 18, background: COLORS.border, borderRadius: 4, overflow: "hidden", position: "relative" }}>
        <div style={{
          width: `${pct}%`,
          height: "100%",
          background: color,
          borderRadius: 4,
          opacity: 0.8,
          float: invert ? "right" : "left",
        }} />
      </div>
      <span style={{ width: 50, fontSize: 11, color: value > 0 ? COLORS.green : COLORS.red, textAlign: "left", flexShrink: 0 }}>
        {value.toFixed(3)}
      </span>
    </div>
  )
}

function MetricCard({ title, value, sub, color }: { title: string; value: string; sub?: string; color: string }) {
  return (
    <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: "16px 20px", flex: 1, minWidth: 140 }}>
      <div style={{ fontSize: 11, color: COLORS.muted, marginBottom: 4 }}>{title}</div>
      <div style={{ fontSize: 24, fontWeight: 700, color }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: COLORS.muted, marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

export default function CryptoPaper() {
  const [data, setData] = useState<Data | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      fetch("/output/crypto/paper_report.json").then(r => r.json()),
      fetch("/output/crypto/signal.json").then(r => r.json()),
    ]).then(([report, signal]) => {
      setData({
        icir_top: report.icir_top || [],
        long_auc: report.long_auc || 0,
        short_auc: report.short_auc || 0,
        oos: report.oos_backtest || { n_trades: 0, total_return_pct: 0, sharpe: 0, max_dd_pct: 0, win_rate_pct: 0, profit_factor: 0 },
        signal: (signal.signals || []).map((s: any) => ({
          action: s.action,
          direction: s.direction,
          confidence: s.confidence,
          price: s.price,
          symbol: s.symbol.replace("/USDT:USDT", ""),
        })),
      })
      setLoading(false)
    })
  }, [])

  if (loading) {
    return <div style={{ padding: 40, color: COLORS.muted, fontFamily: "system-ui" }}>Loading crypto paper results...</div>
  }
  if (!data) {
    return <div style={{ padding: 40, color: COLORS.red, fontFamily: "system-ui" }}>No data found. Run _run_crypto_paper.py first.</div>
  }

  const maxIc = Math.max(...data.icir_top.map(f => Math.abs(f.ic_mean)))

  return (
    <div style={{ background: COLORS.bg, color: COLORS.text, fontFamily: "system-ui, -apple-system, sans-serif", padding: "32px 40px", minHeight: "100vh" }}>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontSize: 12, color: COLORS.muted, letterSpacing: 1, marginBottom: 4 }}>ALPHAPILOT CRYPTO</div>
        <div style={{ fontSize: 28, fontWeight: 800 }}>虚拟量化报告</div>
        <div style={{ fontSize: 13, color: COLORS.muted, marginTop: 4 }}>Binance永续合约 · XGBoost · 4小时级别 · BTC/ETH</div>
      </div>

      {/* Metrics Row */}
      <div style={{ display: "flex", gap: 12, marginBottom: 32, flexWrap: "wrap" }}>
        <MetricCard title="做多模型 AUC" value={data.long_auc.toFixed(4)} sub="1 = 完美, 0.5 = 随机" color={data.long_auc > 0.65 ? COLORS.green : COLORS.amber} />
        <MetricCard title="做空模型 AUC" value={data.short_auc.toFixed(4)} sub="样本外测试集" color={data.short_auc > 0.65 ? COLORS.green : COLORS.amber} />
        <MetricCard title="OOS 交易次数" value={String(data.oos.n_trades)} sub="最后20%时间区间" color={COLORS.text} />
        <MetricCard title="胜率" value={`${data.oos.win_rate_pct.toFixed(1)}%`} sub={data.oos.win_rate_pct > 50 ? "优于随机" : "需优化"} color={data.oos.win_rate_pct > 50 ? COLORS.green : COLORS.red} />
        <MetricCard title="夏普比" value={data.oos.sharpe.toFixed(3)} sub="> 1.0 为优秀" color={data.oos.sharpe > 1 ? COLORS.green : data.oos.sharpe > 0 ? COLORS.amber : COLORS.red} />
      </div>

      {/* Two-column layout */}
      <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
        {/* Left: Factor importance */}
        <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: 20, flex: 1.5, minWidth: 320 }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>因子 ICIR 排名</div>
          <div style={{ fontSize: 11, color: COLORS.muted, marginBottom: 12 }}>IC = 因子与未来收益的秩相关系数 | ICIR = IC / IC标准差（信息比）</div>
          {data.icir_top.map((f, i) => (
            <Bar key={f.factor} label={f.factor} value={f.ic_mean} max={maxIc} color={f.ic_mean < 0 ? COLORS.red : COLORS.green} invert={f.ic_mean < 0} />
          ))}
        </div>

        {/* Right: Current signal + status */}
        <div style={{ flex: 1, minWidth: 280, display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Live signal */}
          <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: 20 }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>当前信号</div>
            {data.signal.length === 0 ? (
              <div style={{ color: COLORS.muted, fontSize: 13 }}>无活跃信号（置信度不足）</div>
            ) : (
              data.signal.map((s, i) => (
                <div key={i} style={{ padding: "10px 0", borderTop: i > 0 ? `1px solid ${COLORS.border}` : "none" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 16, fontWeight: 600 }}>{s.symbol}</span>
                    <span style={{
                      fontSize: 12, fontWeight: 700, padding: "2px 10px", borderRadius: 8,
                      background: s.direction === "short" ? COLORS.red + "22" : COLORS.green + "22",
                      color: s.direction === "short" ? COLORS.red : COLORS.green,
                    }}>
                      {s.direction === "short" ? "做空" : "做多"}
                    </span>
                  </div>
                  <div style={{ display: "flex", gap: 16, marginTop: 6, fontSize: 12, color: COLORS.muted }}>
                    <span>入场: ${s.price.toFixed(2)}</span>
                    <span>置信度: {(s.confidence * 100).toFixed(0)}%</span>
                    <span>{s.action === "enter_long" || s.action === "enter_short" ? "开仓" : s.action}</span>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Interpretation */}
          <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: 20 }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>研判</div>
            <div style={{ fontSize: 12, color: COLORS.muted, lineHeight: 1.6 }}>
              <p><strong style={{ color: COLORS.text }}>模型有效</strong> — 做多 AUC {data.long_auc.toFixed(3)} / 做空 AUC {data.short_auc.toFixed(3)}，优于随机 (0.5)。</p>
              <p><strong style={{ color: COLORS.text }}>最强因子</strong> — MA 均线距离（均值回归效应），短期反转 (ret_1)。</p>
              <p><span style={{ color: COLORS.amber }}>OoS 回测亏损</span> — 交易策略需迭代：出场规则和仓位管理需精细化。</p>
              <p style={{ marginTop: 8 }}>虚拟盘持续运行中 → 统计累计胜率和盈亏比，达标再上实盘。</p>
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div style={{ marginTop: 32, fontSize: 11, color: COLORS.muted, borderTop: `1px solid ${COLORS.border}`, paddingTop: 12 }}>
        AlphaPilot Crypto Paper — {new Date().toISOString().slice(0, 10)}
      </div>
    </div>
  )
}
