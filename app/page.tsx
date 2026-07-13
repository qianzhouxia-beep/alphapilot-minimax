// AlphaPilot Landing Page — AI 驱动智能决策终端
"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { fetchCNIndices, type IndexData } from "@/lib/cn-api";

export default function LandingPage() {
  const [indices, setIndices] = useState<IndexData[] | null>(null);
  const [indicesLoading, setIndicesLoading] = useState(true);
  const shaderRef = useRef<HTMLCanvasElement>(null);
  const threeRef = useRef<HTMLDivElement>(null);

  // ── 实时指数行情 ──
  useEffect(() => {
    let cancelled = false;
    const fetch = async () => {
      try {
        const res = await fetchCNIndices();
        if (!cancelled) setIndices(res.indices);
      } catch { /* fallback to hardcoded */ }
      if (!cancelled) setIndicesLoading(false);
    };
    fetch();
    return () => { cancelled = true; };
  }, []);

  // ── Shader Background ──
  useEffect(() => {
    const canvas = shaderRef.current;
    if (!canvas) return;
    function syncSize() {
      const w = canvas.clientWidth || window.innerWidth;
      const h = canvas.clientHeight || window.innerHeight;
      if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    }
    if (typeof ResizeObserver !== "undefined") { new ResizeObserver(syncSize).observe(canvas); }
    syncSize();
    const gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
    if (!gl) return;
    const vs = `attribute vec2 a_position; varying vec2 v_texCoord; void main() { v_texCoord = a_position * 0.5 + 0.5; gl_Position = vec4(a_position, 0.0, 1.0); }`;
    const fs = `precision highp float; uniform float u_time; uniform vec2 u_resolution; uniform vec2 u_mouse; varying vec2 v_texCoord; void main() { vec2 uv = v_texCoord; vec3 color_bg = vec3(0.027,0.067,0.122); vec3 color_accent = vec3(0.176,0.639,1.0); vec3 color_primary = vec3(0.302,0.639,1.0); float noise = 0.0; vec2 p = uv*2.0-1.0; p.x *= u_resolution.x/u_resolution.y; for(float i=1.0; i<4.0; i++) { p.x += 0.3/i*sin(i*3.0*p.y+u_time*0.5+i); p.y += 0.3/i*cos(i*3.0*p.x+u_time*0.3+i); noise += 0.1/length(p); } vec2 mouse_norm = u_mouse/u_resolution; float dist_to_mouse = distance(uv,mouse_norm); float glow = smoothstep(0.4,0.0,dist_to_mouse)*0.2; vec3 final_color = mix(color_bg,color_accent,noise*0.2); final_color += color_primary*glow; float grid = (step(0.98,fract(uv.x*20.0))+step(0.98,fract(uv.y*20.0)))*0.03; final_color += vec3(grid); gl_FragColor = vec4(final_color,1.0); }`;
    function cs(t: number, s: string) { const sh = gl.createShader(t)!; gl.shaderSource(sh, s); gl.compileShader(sh); return sh; }
    const prog = gl.createProgram()!;
    gl.attachShader(prog, cs(gl.VERTEX_SHADER, vs));
    gl.attachShader(prog, cs(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(prog); gl.useProgram(prog);
    const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1,1,-1,-1,1,1,1]), gl.STATIC_DRAW);
    const pos = gl.getAttribLocation(prog, "a_position");
    gl.enableVertexAttribArray(pos); gl.vertexAttribPointer(pos, 2, gl.FLOAT, false, 0, 0);
    const uTime = gl.getUniformLocation(prog, "u_time");
    const uRes = gl.getUniformLocation(prog, "u_resolution");
    const uMouse = gl.getUniformLocation(prog, "u_mouse");
    let mouse = { x: canvas.width/2, y: canvas.height/2 };
    const onMouse = (e: MouseEvent) => { const r = canvas.getBoundingClientRect(); if (r.width && r.height) { mouse.x = ((e.clientX-r.left)/r.width)*canvas.width; mouse.y = (1.0-(e.clientY-r.top)/r.height)*canvas.height; } };
    window.addEventListener("mousemove", onMouse);
    let anim = 0;
    function render(t: number) { syncSize(); gl.viewport(0,0,canvas.width,canvas.height); if (uTime) gl.uniform1f(uTime, t*0.001); if (uRes) gl.uniform2f(uRes, canvas.width, canvas.height); if (uMouse) gl.uniform2f(uMouse, mouse.x, mouse.y); gl.drawArrays(gl.TRIANGLE_STRIP,0,4); anim = requestAnimationFrame(render); }
    render(0);
    return () => { cancelAnimationFrame(anim); window.removeEventListener("mousemove", onMouse); };
  }, []);

  // ── Three.js AI Core ──
  useEffect(() => {
    const container = threeRef.current;
    if (!container) return;
    let anim = 0, renderer: any, scene: any, camera: any, coreGroup: any, rings: any[] = [];
    import("three").then((THREE) => {
      const w = container.clientWidth, h = container.clientHeight;
      scene = new THREE.Scene();
      camera = new THREE.PerspectiveCamera(75, w/h, 0.1, 1000);
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      renderer.setPixelRatio(window.devicePixelRatio); renderer.setSize(w, h);
      container.appendChild(renderer.domElement);
      scene.add(new THREE.AmbientLight(0xffffff, 0.5));
      const pl = new THREE.PointLight(0x4da3ff, 2); pl.position.set(5,5,5); scene.add(pl);
      coreGroup = new THREE.Group();
      coreGroup.add(new THREE.Mesh(new THREE.SphereGeometry(0.8,32,32), new THREE.MeshPhongMaterial({ color: 0x2dd4ff, emissive: 0x0a1422, shininess: 100, transparent: true, opacity: 0.8 })));
      const ringMat = new THREE.MeshBasicMaterial({ color: 0x4da3ff, transparent: true, opacity: 0.4 });
      [1.5,1.8,2.1].forEach((r) => { const ring = new THREE.Mesh(new THREE.TorusGeometry(r,0.02,16,100), ringMat); ring.rotation.x = Math.random()*Math.PI; ring.rotation.y = Math.random()*Math.PI; coreGroup.add(ring); rings.push(ring); });
      scene.add(coreGroup); camera.position.z = 5;
      let mx = 0, my = 0;
      window.addEventListener("mousemove", (e) => { mx = (e.clientX/window.innerWidth)*2-1; my = -(e.clientY/window.innerHeight)*2+1; });
      window.addEventListener("resize", () => { const nw = container.clientWidth, nh = container.clientHeight; camera.aspect = nw/nh; camera.updateProjectionMatrix(); renderer.setSize(nw, nh); });
      function animate() { anim = requestAnimationFrame(animate); coreGroup.rotation.y += 0.005; coreGroup.rotation.x += 0.002; rings.forEach((r: any,i) => { r.rotation.z += 0.01*(i+1); r.rotation.x += 0.005*(i+1); }); coreGroup.position.x += (mx*0.5-coreGroup.position.x)*0.05; coreGroup.position.y += (my*0.5-coreGroup.position.y)*0.05; renderer.render(scene, camera); }
      animate();
    });
    return () => { cancelAnimationFrame(anim); if (renderer && renderer.domElement) renderer.domElement.remove(); };
  }, []);

  return (
    <div className="relative min-h-screen bg-background text-text-primary font-['Inter','Microsoft_YaHei',sans-serif] overflow-x-hidden">
      <style jsx>{`
        @keyframes fadeInUp { from { opacity:0; transform:translateY(20px); } to { opacity:1; transform:translateY(0); } }
        @keyframes float { 0%{transform:translateY(0px)} 50%{transform:translateY(-10px)} 100%{transform:translateY(0px)} }
        .animate-fade-in-up { animation:fadeInUp 0.8s cubic-bezier(0.16,1,0.3,1) forwards; }
        .glass-panel { background:rgba(16,28,48,0.6); backdrop-filter:blur(16px); border:1px solid rgba(29,42,66,0.5); }
        .no-scrollbar::-webkit-scrollbar { display:none; }
        .no-scrollbar { -ms-overflow-style:none; scrollbar-width:none; }
      `}</style>

      {/* Top Navigation */}
      <nav className="fixed top-0 w-full z-50 bg-background/80 backdrop-blur-xl border-b border-border-subtle/50 shadow-sm">
        <div className="flex justify-between items-center h-16 px-8 max-w-[1440px] mx-auto">
          <div className="flex items-center gap-4">
            <Link href="/"><Image src="/logo.png" alt="AlphaPilot" className="h-8 w-auto" width={140} height={32} priority /></Link>
          </div>
          <div className="hidden md:flex items-center gap-6">
            <Link href="/cn" className="text-text-primary font-bold border-b-2 border-[#a2c9ff] pb-1 text-[13px]">智能决策终端</Link>
            <Link href="/cn" className="text-text-secondary hover:text-text-primary transition-colors text-[13px]">A 股选股</Link>
            <Link href="/cn/watchlist" className="text-text-secondary hover:text-text-primary transition-colors text-[13px]">收藏追踪</Link>
            <Link href="/cn/paper-trading" className="text-text-secondary hover:text-text-primary transition-colors text-[13px]">量化模拟盘</Link>
            <Link href="/cn/news" className="text-text-secondary hover:text-text-primary transition-colors text-[13px]">投资资讯</Link>
          </div>
          <div className="flex items-center gap-4">
            <Link href="/cn" className="bg-status-info text-[#003866] px-6 py-2 rounded-lg text-[13px] font-medium active:scale-95 duration-200 transition-all hover:brightness-110">立即体验</Link>
          </div>
        </div>
      </nav>

      <main className="relative pt-16">
        {/* HERO */}
        <section className="relative min-h-[90vh] flex items-center overflow-hidden">
          <div className="absolute inset-0 z-0 opacity-40"><canvas ref={shaderRef} className="w-full h-full" /></div>
          <div className="relative z-10 w-full max-w-[1440px] mx-auto px-8 grid grid-cols-1 lg:grid-cols-2 gap-6 items-center">
            <div className="animate-fade-in-up" style={{ animationDelay:"0.2s" }}>
              <span className="inline-flex items-center px-3 py-1 rounded-full bg-[#a2c9ff]/10 border border-[#a2c9ff]/20 text-text-primary text-[12px] font-medium mb-4">
                <span className="w-2 h-2 rounded-full bg-[#a2c9ff] mr-2 animate-pulse" />V18 Fusion 决策系统已就绪
              </span>
              <h1 className="text-[32px] md:text-[56px] md:leading-[64px] font-bold text-text-primary tracking-tight mb-4">
                AI 驱动量价穿透 <br />
                <span className="text-transparent bg-clip-text bg-gradient-to-r from-[#a2c9ff] to-[#7ddeff]">洞察主力意图的决策终端</span>
              </h1>
              {/* Market Indices */}
              <div className="flex gap-4 mb-6 overflow-x-auto pb-2 no-scrollbar">
                {(indices || [
                  { name:"上证指数", price:3052.81, change_pct:0.45, change:13.68 } as any,
                  { name:"深证成指", price:9432.55, change_pct:-0.12, change:-11.32 } as any,
                  { name:"创业板指", price:1826.44, change_pct:0.68, change:12.36 } as any,
                ]).map((idx) => {
                  const chg = idx.change_pct ?? 0;
                  const isUp = chg >= 0;
                  // A 股惯例：涨→红(#FF5D5D) 跌→绿(#35e0a3)
                  const color = isUp ? "#FF5D5D" : "#35e0a3";
                  return (
                  <div key={idx.name} className="glass px-4 py-2 rounded-lg flex flex-col min-w-[120px]">
                    <span className="text-[12px] text-text-secondary">{idx.name}</span>
                    <div className="flex items-center gap-2">
                      <span className="font-bold" style={{ color }}>{idx.price.toFixed(2)}</span>
                      <span className="text-[10px]" style={{ color }}>{isUp ? "+" : ""}{chg.toFixed(2)}%</span>
                    </div>
                    {indicesLoading && <div className="h-3 w-16 bg-[#1D2A42] rounded mt-1 animate-pulse" />}
                  </div>
                )})}
              </div>
              <p className="text-[16px] text-text-secondary max-w-lg mb-6 leading-relaxed">
                融合深度神经网络与量价行为分析，精准锁定机构建仓信号。
                30维融合特征 + 5模型集成数据，用机构级的视角穿透市场迷雾。
              </p>
              <div className="flex flex-col sm:flex-row gap-4">
                <Link href="/cn" className="bg-status-info text-[#003866] px-8 py-4 rounded-xl text-[20px] font-semibold hover:brightness-110 active:scale-95 transition-all shadow-lg shadow-[#4da3ff]/20 text-center">立即体验智能决策</Link>
                <Link href="/cn/watchlist" className="glass text-text-primary px-8 py-4 rounded-xl text-[20px] font-semibold hover:bg-[#212a39] transition-all flex items-center justify-center gap-2">⭐ 收藏追踪</Link>
              </div>
            </div>
            <div className="hidden lg:block relative h-[600px] animate-fade-in-up" style={{ animationDelay:"0.4s" }}>
              <div ref={threeRef} className="w-full h-full" />
              <div className="absolute top-10 right-0 glass p-4 rounded-xl border-border-subtle">
                <div className="flex items-center gap-2 text-text-primary"><span className="text-[13px] font-bold uppercase tracking-widest">⚡ 主力意图：积极吸筹</span></div>
              </div>
            </div>
          </div>
        </section>

        {/* Trust Stats */}
        <section className="py-6 border-y border-border-subtle bg-[#050e1c]/50 backdrop-blur-md">
          <div className="max-w-[1440px] mx-auto px-8 grid grid-cols-2 md:grid-cols-4 gap-5 text-center">
            {[{ label:"波段胜率", value:"84%", color:"#35e0a3" },{ label:"平均盈亏比", value:"3.2:1", color:"#a2c9ff" },{ label:"每日决策信号", value:"500+", color:"#EAF2FF" },{ label:"行情响应延迟", value:"5ms", color:"#7ddeff" }].map((s) => (
              <div key={s.label} className="space-y-1">
                <p className="text-text-secondary text-[12px] uppercase tracking-widest font-medium">{s.label}</p>
                <p className="text-[36px] font-bold leading-[44px] tracking-tight" style={{ color: s.color }}>{s.value}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Feature Highlights */}
        <section className="py-16 px-8 max-w-[1200px] mx-auto">
          <div className="text-center mb-12">
            <h2 className="text-[30px] font-semibold mb-3 text-text-primary">全维度决策分析矩阵</h2>
            <p className="text-text-secondary text-[15px] max-w-2xl mx-auto">V18 Fusion 决策系统 · 30维融合特征 · 5模型集成 · 动态止盈止损</p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Card 1: 主力行为雷达 */}
            <div className="glass card-lift rounded-2xl p-5 flex flex-col h-full hover:border-[#4DA3FF]/40 transition-all">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-[rgba(77,163,255,0.12)] flex items-center justify-center">
                    <svg className="w-5 h-5 text-status-info" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 2a10 10 0 0 1 10 10"/><path d="M12 6a6 6 0 0 1 6 6"/><path d="M12 10a2 2 0 0 1 2 2"/>
                      <path d="M12 22a10 10 0 0 1-10-10"/><path d="M12 18a6 6 0 0 1-6-6"/><path d="M12 14a2 2 0 0 1-2-2"/>
                      <circle cx="12" cy="12" r="2" fill="currentColor" stroke="none"/>
                    </svg>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase tracking-wider text-status-info font-medium">监测</span>
                    <h3 className="text-[17px] font-semibold text-text-primary">主力行为雷达</h3>
                  </div>
                </div>
                <span className="text-[11px] text-status-success bg-[rgba(62,230,168,0.1)] px-2 py-0.5 rounded-full border border-[rgba(62,230,168,0.25)]">实时追踪</span>
              </div>
              <p className="text-[13px] text-text-secondary mb-4 leading-relaxed">30维融合特征穿透式监控主力资金动向，结合5模型集成数据验证持仓分布。</p>
              <div className="mt-auto grid grid-cols-2 gap-3">
                <div className="bg-surface-container-low p-3 rounded-xl border border-border-subtle">
                  <div className="flex justify-between mb-2"><span className="text-[11px] text-text-secondary">机构持续流入</span><span className="text-[11px] font-semibold text-status-success">极高</span></div>
                  <div className="h-1.5 bg-[#2c3545] rounded-full overflow-hidden"><div className="h-full rounded-full bg-[#3EE6A8]" style={{width:"88%"}} /></div>
                </div>
                <div className="bg-surface-container-low p-3 rounded-xl border border-border-subtle">
                  <div className="flex justify-between mb-2"><span className="text-[11px] text-text-secondary">短期过热预警</span><span className="text-[11px] font-semibold text-status-warning">中风险</span></div>
                  <div className="h-1.5 bg-[#2c3545] rounded-full overflow-hidden"><div className="h-full rounded-full bg-[#F5C451]" style={{width:"45%"}} /></div>
                </div>
              </div>
            </div>

            {/* Card 2: 量化信号筛选 */}
            <div className="glass card-lift rounded-2xl p-5 flex flex-col h-full hover:border-[#3EE6A8]/40 transition-all">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-[rgba(62,230,168,0.12)] flex items-center justify-center">
                    <svg className="w-5 h-5 text-status-success" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="4" y1="6" x2="20" y2="6"/><line x1="6" y1="10" x2="18" y2="10"/>
                      <line x1="8" y1="14" x2="16" y2="14"/><line x1="10" y1="18" x2="14" y2="18"/>
                    </svg>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase tracking-wider text-status-success font-medium">选股</span>
                    <h3 className="text-[17px] font-semibold text-text-primary">量化信号筛选</h3>
                  </div>
                </div>
                <span className="text-[11px] text-status-warning bg-[rgba(245,196,81,0.1)] px-2 py-0.5 rounded-full border border-[rgba(245,196,81,0.25)]">Top 1%</span>
              </div>
              <p className="text-[13px] text-text-secondary mb-4 leading-relaxed">基于XGBoost集成模型，对全市场5000+标的进行多维度穿透评分，精选明日涨幅≥3%标的。</p>
              <div className="mt-auto bg-surface-container-low rounded-xl p-3 border border-border-subtle">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[11px] text-text-secondary">V18 Fusion 评分</span>
                  <span className="text-[18px] font-bold text-status-success">96.8</span>
                </div>
                <div className="flex gap-2 text-[11px] text-text-secondary">
                  <span>30维融合特征深度扫描</span>
                  <span className="text-text-disabled">·</span>
                  <span>门控过滤通过</span>
                </div>
              </div>
            </div>

            {/* Card 3: 资金阶段识别 */}
            <div className="glass card-lift rounded-2xl p-5 flex flex-col h-full hover:border-[#F5C451]/40 transition-all">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-[rgba(245,196,81,0.12)] flex items-center justify-center">
                    <svg className="w-5 h-5 text-status-warning" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                    </svg>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase tracking-wider text-status-warning font-medium">阶段</span>
                    <h3 className="text-[17px] font-semibold text-text-primary">资金阶段识别</h3>
                  </div>
                </div>
                <span className="text-[11px] text-[#A78BFA] bg-[rgba(139,92,246,0.1)] px-2 py-0.5 rounded-full border border-[rgba(139,92,246,0.25)]">9大阶段</span>
              </div>
              <p className="text-[13px] text-text-secondary mb-4 leading-relaxed">智能识别吸筹、拉升、出货、诱多等9种资金运作阶段，只参与拉升和右侧潜伏交易。</p>
              <div className="mt-auto grid grid-cols-3 gap-2">
                <div className="bg-surface-container-low p-2.5 rounded-xl border border-border-subtle text-center">
                    <svg className="mx-auto mb-1" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FF5D5D" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>
                    </svg>
                    <div className="text-[11px] font-medium text-status-danger">拉升</div>
                    <div className="h-1 bg-[#2c3545] rounded-full overflow-hidden mt-1"><div className="h-full rounded-full bg-[#FF5D5D]" style={{width:"78%"}} /></div>
                  </div>
                  <div className="bg-surface-container-low p-2.5 rounded-xl border border-border-subtle text-center">
                    <svg className="mx-auto mb-1" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#F59E0B" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2" fill="#F59E0B" stroke="none"/>
                    </svg>
                    <div className="text-[11px] font-medium text-[#F59E0B]">潜伏</div>
                    <div className="h-1 bg-[#2c3545] rounded-full overflow-hidden mt-1"><div className="h-full rounded-full bg-[#F59E0B]" style={{width:"62%"}} /></div>
                  </div>
                  <div className="bg-surface-container-low p-2.5 rounded-xl border border-border-subtle text-center">
                    <svg className="mx-auto mb-1" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#3B82F6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="12" y1="2" x2="12" y2="15"/><polyline points="5 8 12 15 19 8"/><line x1="4" y1="20" x2="20" y2="20"/>
                    </svg>
                    <div className="text-[11px] font-medium text-[#3B82F6]">吸筹</div>
                    <div className="h-1 bg-[#2c3545] rounded-full overflow-hidden mt-1"><div className="h-full rounded-full bg-[#3B82F6]" style={{width:"70%"}} /></div>
                  </div>
              </div>
            </div>

            {/* Card 4: 动态风控引擎 */}
            <div className="glass card-lift rounded-2xl p-5 flex flex-col h-full hover:border-[#FF5D5D]/40 transition-all">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-[rgba(255,93,93,0.12)] flex items-center justify-center">
                    <svg className="w-5 h-5 text-status-danger" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                    </svg>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase tracking-wider text-status-danger font-medium">风控</span>
                    <h3 className="text-[17px] font-semibold text-text-primary">动态风控引擎</h3>
                  </div>
                </div>
                <span className="text-[11px] text-status-success bg-[rgba(62,230,168,0.1)] px-2 py-0.5 rounded-full border border-[rgba(62,230,168,0.25)]">自动止损</span>
              </div>
              <p className="text-[13px] text-text-secondary mb-4 leading-relaxed">动态追踪止盈 · 自动硬止损 · 单票仓位上限30% · 最大回撤-8%暂停交易，护航每一笔交易。</p>
              <div className="mt-auto flex flex-col gap-2">
                <div className="flex items-center justify-between bg-surface-container-low px-3 py-2 rounded-lg border border-border-subtle">
                  <span className="text-[12px] text-text-secondary">追涨止盈</span>
                  <span className="text-[12px] text-status-success font-mono">+3%/+5%/+8%/+12%</span>
                </div>
                <div className="flex items-center justify-between bg-surface-container-low px-3 py-2 rounded-lg border border-border-subtle">
                  <span className="text-[12px] text-text-secondary">硬止损线</span>
                  <span className="text-[12px] text-status-danger font-mono">-3%减半 / -5%清仓</span>
                </div>
              </div>
            </div>
          </div>

          {/* Bottom CTA bar */}
          <div className="mt-6 glass rounded-2xl p-4 flex items-center justify-between border-l-4 border-l-[#4DA3FF]">
            <div className="flex items-center gap-3">
              <svg className="w-8 h-8 text-status-info shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
              </svg>
              <div>
                <p className="text-[14px] font-semibold text-text-primary">V18 Fusion 决策系统已就绪</p>
                <p className="text-[12px] text-text-secondary">每日凌晨5:00全量扫描 · 今日已有更新数据</p>
              </div>
            </div>
            <Link href="/cn" className="bg-status-info text-[#003866] px-5 py-2.5 rounded-lg text-[13px] font-semibold hover:brightness-110 transition-all shrink-0">进入智能决策终端</Link>
          </div>
        </section>

        {/* CTA */}
        <section className="relative py-24 overflow-hidden">
          <div className="absolute inset-0 bg-[#a2c9ff]/5 -skew-y-3 scale-y-110" />
          <div className="relative z-10 max-w-[1440px] mx-auto px-8 text-center">
            <h2 className="text-[32px] font-semibold mb-4">准备好开启智能交易时代了吗？</h2>
            <p className="text-text-secondary text-[16px] max-w-xl mx-auto mb-6">V18 Fusion 决策系统 · 30维融合特征 · 5模型集成</p>
            <div className="flex flex-col sm:flex-row justify-center items-center gap-4">
              <Link href="/cn" className="bg-status-info text-[#003866] px-10 py-5 rounded-xl text-[20px] font-semibold shadow-2xl shadow-[#4da3ff]/40 hover:scale-105 active:scale-95 transition-all">立即体验</Link>
              <p className="text-text-disabled text-[12px]">无需注册 · 即享全功能访问</p>
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="bg-[#050e1c] border-t border-border-subtle w-full py-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 px-8 max-w-[1440px] mx-auto items-center">
          <div className="space-y-2">
            <Image src="/logo.png" alt="AlphaPilot" className="h-6 w-auto opacity-80" width={120} height={24} />
            <p className="text-[12px] text-text-secondary max-w-xs">© 2026 AlphaPilot AI. 专为现代投资者打造的机构级智能决策终端。</p>
          </div>
          <div className="flex flex-wrap md:justify-end gap-x-6 gap-y-2">
            {["服务协议","隐私政策","风险揭示","技术支持"].map((t) => (<a key={t} href="#" className="text-[12px] text-text-secondary hover:text-text-primary transition-colors">{t}</a>))}
          </div>
        </div>
        <div className="max-w-[1440px] mx-auto px-8 mt-4 pt-4 border-t border-border-subtle/30 text-[10px] text-text-disabled leading-relaxed">市场有风险，投资需谨慎。AlphaPilot 提供的 AI 模型分析仅供参考，不构成任何投资建议或决策依据。</div>
      </footer>
    </div>
  );
}