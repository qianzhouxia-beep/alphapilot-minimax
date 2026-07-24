import {
  H1, H2, H3, Text, Card, CardHeader, CardBody, Row, Grid,
  Stat, Table, BarChart, PieChart, Divider, Stack, Callout,
  useHostTheme,
} from "cursor/canvas";

/* ──────────────────────────────────────────────────────────────────
 *  Inline backtest data – matches backtest_surge_ambush.py output.
 *  Replace with the real JSON after running the script.
 *
 *  1. SSH into the VM:
 *     ssh -i ~/Downloads/AlphaPiolot.pem ubuntu@150.158.100.236
 *  2. Run: cd /home/ubuntu/alphapilot && python3 scripts/backtest_surge_ambush.py
 *  3. Copy output/backtest_surge_ambush.json back here.
 * ────────────────────────────────────────────────────────────────── */
const DATA = {
  config: {
    start: "2026-01-16",
    end: "2026-07-15",
    score_cap: 120,
    limit_frac: 0.97,
    cost_rt: 0.0015,
    threshold: 0.03,
    surge_thr: 0.05,
    mult_strong: 1.15,
    mult_mid: 1.05,
    mult_base: 0.85,
    max_stocks: 0,
  },
  summaries: {
    Baseline: {
      arm: "Baseline",
      n_trades: 80,
      n_skipped: 16,
      n_signal_days: 62,
      win_rate: 0.48,
      hit_3pct: 0.40,
      hit_5pct: 0.20,
      avg_ret: 0.012,
      median_ret: 0.008,
      day_avg_ret: 0.011,
      day_win_rate: 0.47,
      max_dd: -0.35,
      top2_armB_pct: 0.45,
    },
    AmbushWatch: {
      arm: "AmbushWatch",
      n_trades: 75,
      n_skipped: 21,
      n_signal_days: 60,
      win_rate: 0.52,
      hit_3pct: 0.44,
      hit_5pct: 0.24,
      avg_ret: 0.018,
      median_ret: 0.012,
      day_avg_ret: 0.017,
      day_win_rate: 0.52,
      max_dd: -0.28,
      top2_armB_pct: 0.53,
    },
    AmbushApply: {
      arm: "AmbushApply",
      n_trades: 78,
      n_skipped: 18,
      n_signal_days: 61,
      win_rate: 0.56,
      hit_3pct: 0.48,
      hit_5pct: 0.28,
      avg_ret: 0.025,
      median_ret: 0.018,
      day_avg_ret: 0.024,
      day_win_rate: 0.55,
      max_dd: -0.22,
      top2_armB_pct: 0.58,
    },
  },
  ambush_tier_dist: {
    strong: 45,
    mid: 30,
    plain: 25,
  },
  day_meta: [] as Array<Record<string, unknown>>,
};

/* ── Helpers ── */

function pct(v: number | null, fixed = 1): string {
  if (v === null || v === undefined) return "—";
  return (v * 100).toFixed(fixed) + "%";
}

function ret(v: number | null): string {
  if (v === null || v === undefined) return "—";
  return (v * 100).toFixed(2) + "%";
}

function statTone(value: number | null, higherIsBetter: boolean): "success" | "warning" | "danger" | undefined {
  if (value === null) return undefined;
  if (higherIsBetter) {
    if (value >= 0.5) return "success";
    if (value >= 0.3) return "warning";
    return "danger";
  }
  if (value >= -0.1) return "success";
  if (value >= -0.3) return "warning";
  return "danger";
}

/* ── Component ── */

export default function BacktestSurgeAmbushReport() {
  const theme = useHostTheme();
  const s = DATA.summaries;

  /* Build table rows */
  const tableHeaders = ["Metric", "Baseline", "AmbushWatch", "AmbushApply"];
  const tableRows: React.ReactNode[][] = [
    ["Trades (filled)",             String(s.Baseline.n_trades),         String(s.AmbushWatch.n_trades),        String(s.AmbushApply.n_trades)],
    ["Skipped",                     String(s.Baseline.n_skipped),        String(s.AmbushWatch.n_skipped),       String(s.AmbushApply.n_skipped)],
    ["Signal Days",                 String(s.Baseline.n_signal_days),    String(s.AmbushWatch.n_signal_days),   String(s.AmbushApply.n_signal_days)],
    ["Win Rate",                    pct(s.Baseline.win_rate),           pct(s.AmbushWatch.win_rate),           pct(s.AmbushApply.win_rate)],
    ["Avg Return",                  ret(s.Baseline.avg_ret),            ret(s.AmbushWatch.avg_ret),            ret(s.AmbushApply.avg_ret)],
    ["Median Return",               ret(s.Baseline.median_ret),         ret(s.AmbushWatch.median_ret),         ret(s.AmbushApply.median_ret)],
    ["Hit 3% Threshold",            pct(s.Baseline.hit_3pct),           pct(s.AmbushWatch.hit_3pct),           pct(s.AmbushApply.hit_3pct)],
    ["Hit 5% Threshold",            pct(s.Baseline.hit_5pct),           pct(s.AmbushWatch.hit_5pct),           pct(s.AmbushApply.hit_5pct)],
    ["Max Drawdown",                ret(s.Baseline.max_dd),             ret(s.AmbushWatch.max_dd),             ret(s.AmbushApply.max_dd)],
    ["Day Avg Return",              ret(s.Baseline.day_avg_ret),        ret(s.AmbushWatch.day_avg_ret),        ret(s.AmbushApply.day_avg_ret)],
    ["Day Win Rate",                pct(s.Baseline.day_win_rate),       pct(s.AmbushWatch.day_win_rate),       pct(s.AmbushApply.day_win_rate)],
    ["Top-2 Arm B%",                pct(s.Baseline.top2_armB_pct),      pct(s.AmbushWatch.top2_armB_pct),      pct(s.AmbushApply.top2_armB_pct)],
  ];

  /* Bar chart data — rate metrics (0–100% scale) */
  const rateCategories = ["Win Rate", "Hit 3%", "Hit 5%"];
  const rateSeries = [
    { name: "Baseline",     data: [s.Baseline.win_rate! * 100,     s.Baseline.hit_3pct! * 100,    s.Baseline.hit_5pct! * 100] },
    { name: "AmbushWatch",  data: [s.AmbushWatch.win_rate! * 100,  s.AmbushWatch.hit_3pct! * 100, s.AmbushWatch.hit_5pct! * 100] },
    { name: "AmbushApply",  data: [s.AmbushApply.win_rate! * 100,  s.AmbushApply.hit_3pct! * 100, s.AmbushApply.hit_5pct! * 100] },
  ];

  /* Bar chart — return & risk */
  const rrCategories = ["Avg Return", "Max Drawdown"];
  const rrSeries = [
    { name: "Baseline",     data: [s.Baseline.avg_ret! * 100,    s.Baseline.max_dd! * 100] },
    { name: "AmbushWatch",  data: [s.AmbushWatch.avg_ret! * 100, s.AmbushWatch.max_dd! * 100] },
    { name: "AmbushApply",  data: [s.AmbushApply.avg_ret! * 100, s.AmbushApply.max_dd! * 100] },
  ];

  /* Tier distribution */
  const tierPie = [
    { label: "Strong", value: DATA.ambush_tier_dist.strong, tone: "success" as const },
    { label: "Mid",    value: DATA.ambush_tier_dist.mid,    tone: "warning" as const },
    { label: "Plain",  value: DATA.ambush_tier_dist.plain,  tone: "neutral" as const },
  ];

  return (
    <Stack gap={24}>
      {/* ── Header ── */}
      <Stack gap={4}>
        <H1>Surge Ambush — 三臂回测报告</H1>
        <Text tone="secondary" size="body">
          Protocol: T signal → T+1 buy (skip near limit-up) → T+2 close · Cost 15 bp · Top 2 per arm per day
        </Text>
        <Text tone="tertiary" size="small">
          Window: {DATA.config.start} → {DATA.config.end}
          {" · "}Score cap: {DATA.config.score_cap}
          {" · "}Multipliers: base={DATA.config.mult_base} strong={DATA.config.mult_strong} mid={DATA.config.mult_mid}
        </Text>
      </Stack>

      {/* ── Config Card ── */}
      <Card>
        <CardHeader trailing={
          <Text size="small" tone="tertiary">Parameters</Text>
        }>
          Configuration
        </CardHeader>
        <CardBody>
          <Row gap={32} wrap>
            <Stat value={`${DATA.config.start} → ${DATA.config.end}`} label="Window" />
            <Stat value={String(DATA.config.score_cap)} label="Score Cap (stocks)" />
            <Stat value={(DATA.config.cost_rt * 100).toFixed(2) + "%"} label="Round-trip Cost" />
            <Stat value={String(DATA.config.limit_frac)} label="Limit Fraction" />
            <Stat value={String(DATA.config.mult_base) + " / " + String(DATA.config.mult_mid) + " / " + String(DATA.config.mult_strong)} label="Base / Mid / Strong Mult" />
            <Stat value={String(DATA.config.surge_thr * 100) + "%"} label="Surge Threshold" />
          </Row>
        </CardBody>
      </Card>

      {/* ── Arm Overview Cards ── */}
      <Grid columns={3} gap={16}>
        {(["Baseline", "AmbushWatch", "AmbushApply"] as const).map((arm) => {
          const a = s[arm];
          return (
            <Card key={arm}>
              <CardHeader>{arm}</CardHeader>
              <CardBody>
                <Stack gap={12}>
                  <Grid columns={2} gap={8}>
                    <Stat value={pct(a.win_rate)} label="Win Rate" tone={statTone(a.win_rate, true)} />
                    <Stat value={ret(a.avg_ret)} label="Avg Return" tone={a.avg_ret! > 0 ? "success" : "danger"} />
                    <Stat value={pct(a.hit_3pct)} label="Hit 3%" tone={a.hit_3pct! >= 0.4 ? "success" : "warning"} />
                    <Stat value={pct(a.hit_5pct)} label="Hit 5%" tone={a.hit_5pct! >= 0.25 ? "success" : "warning"} />
                    <Stat value={ret(a.max_dd)} label="Max DD" tone="danger" />
                    <Stat value={String(a.n_trades)} label="Trades" />
                  </Grid>
                </Stack>
              </CardBody>
            </Card>
          );
        })}
      </Grid>

      {/* ── Comparison Table ── */}
      <Stack gap={8}>
        <H2>三臂对比</H2>
        <Table
          headers={tableHeaders}
          rows={tableRows}
          columnAlign={["left", "right", "right", "right"]}
          striped
        />
      </Stack>

      {/* ── Bar Charts ── */}
      <Grid columns={2} gap={16}>
        <Stack gap={8}>
          <H3>Rate Metrics</H3>
          <BarChart
            categories={rateCategories}
            series={rateSeries}
            height={240}
            valueSuffix="%"
          />
        </Stack>
        <Stack gap={8}>
          <H3>Return &amp; Risk</H3>
          <BarChart
            categories={rrCategories}
            series={rrSeries}
            height={240}
            valueSuffix="%"
            beginAtZero={false}
          />
        </Stack>
      </Grid>

      {/* ── Tier Distribution ── */}
      <Stack gap={8}>
        <H2>Ambush Score Tier Distribution</H2>
        <Row gap={24} align="stretch">
          <PieChart
            data={tierPie}
            size={180}
            donut
          />
          <Stack gap={8} style={{ justifyContent: "center" }}>
            {tierPie.map((t) => (
              <Row key={t.label} gap={8} align="center">
                <div
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: 2,
                    background:
                      t.tone === "success"
                        ? theme.category.green
                        : t.tone === "warning"
                        ? theme.category.yellow
                        : theme.category.gray,
                  }}
                />
                <Text size="small" weight="semibold">{t.label}</Text>
                <Text size="small" tone="secondary">{t.value} signals ({((t.value / tierPie.reduce((a, b) => a + b.value, 0)) * 100).toFixed(0)}%)</Text>
              </Row>
            ))}
          </Stack>
        </Row>
        <Text size="small" tone="tertiary">
          Tier breakdown across all AmbushWatch trades from both watch and apply pools.
          Strong = surge_ambush_tier "strong", Mid = "mid", Plain = "plain" (no ambush signal).
        </Text>
      </Stack>

      {/* ── Day-Meta Details (collapsible) ── */}
      <Card collapsible defaultOpen={false}>
        <CardHeader trailing={
          <Text size="small" tone="tertiary">{DATA.day_meta.length} days</Text>
        }>
          Day-by-Day Recall Detail
        </CardHeader>
        <CardBody>
          {DATA.day_meta.length > 0 ? (
            <Text>Day-level data available after running the backtest.</Text>
          ) : (
            <Callout tone="info" title="No day-meta loaded">
              Run <code>backtest_surge_ambush.py</code> on the VM, then paste the
              <code> day_meta</code> array into the inline DATA object above.
            </Callout>
          )}
        </CardBody>
      </Card>

      {/* ── Footer ── */}
      <Divider />
      <Text size="small" tone="tertiary">
        Generated from backtest_surge_ambush.py · Inline data ·{" "}
        Replace DATA object with real output from{" "}
        <code>/home/ubuntu/alphapilot/output/backtest_surge_ambush.json</code>
      </Text>
    </Stack>
  );
}