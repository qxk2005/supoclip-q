"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Scissors,
  Sparkles,
  Youtube,
  Github,
  ArrowRight,
  Play,
  Target,
  ScanFace,
  Type,
  Film,
  MonitorPlay,
  Share2,
  Wand2,
  ChevronDown,
  ExternalLink,
  Check,
  Infinity,
  Zap,
  Menu,
  X,
} from "lucide-react";
import { isLandingOnlyModeEnabled } from "@/lib/app-flags";

const HOSTED_APP_URL = "https://supoclip.com";

function ScrollReveal({
  children,
  className = "",
  delay = 0,
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
          observer.unobserve(entry.target);
        }
      },
      { threshold: 0.1, rootMargin: "0px 0px -60px 0px" }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={className}
      style={{
        opacity: isVisible ? 1 : 0,
        transform: isVisible ? "translateY(0)" : "translateY(30px)",
        transition: `opacity 0.7s cubic-bezier(0.16, 1, 0.3, 1) ${delay}s, transform 0.7s cubic-bezier(0.16, 1, 0.3, 1) ${delay}s`,
      }}
    >
      {children}
    </div>
  );
}

const FEATURES = [
  {
    icon: ScanFace,
    title: "人脸居中裁切",
    description:
      "MediaPipe 与 OpenCV 检测并跟踪人脸，实现理想的 9:16 竖屏构图。",
  },
  {
    icon: Type,
    title: "逐字同步字幕",
    description:
      "词级时间轴驱动每条片段上精准、带动画的字幕。",
  },
  {
    icon: Target,
    title: "传播力评分",
    description:
      "AI 评估钩子、互动、价值与分享潜力，综合得分 0–100。",
  },
  {
    icon: Film,
    title: "B-Roll 叠加",
    description:
      "自动从 Pexels 匹配并叠加相关素材画面。",
  },
  {
    icon: Sparkles,
    title: "字幕模板",
    description:
      "多种动效与字体预设，贴合你的品牌风格。",
  },
  {
    icon: MonitorPlay,
    title: "平台导出",
    description:
      "一键预设适配 TikTok、Reels、Shorts，编码已优化。",
  },
];

function getPlans() {
  const proPriceMonthly = process.env.NEXT_PUBLIC_PRO_PRICE_MONTHLY || "9.99";
  const freeLimit = parseInt(process.env.NEXT_PUBLIC_FREE_PLAN_TASK_LIMIT || "10", 10);
  const proLimit = parseInt(process.env.NEXT_PUBLIC_PRO_PLAN_TASK_LIMIT || "0", 10);

  const proGenerationsLabel =
    proLimit === 0 ? "每月无限次生成" : `每月 ${proLimit} 次生成`;

  return [
    {
      name: "自托管",
      price: "$0",
      period: "永久",
      description: "在你自己的基础设施上运行，完全自主可控。",
      features: [
        "人脸居中裁切",
        "逐字同步字幕",
        "传播力评分",
        "全部导出预设",
        "完整源代码",
      ],
      cta: "在 GitHub 查看",
      ctaHref: "https://github.com/FujiwaraChoki/supoclip",
      highlighted: false,
      isUnlimited: false,
    },
    {
      name: "Pro",
      price: `$${proPriceMonthly}`,
      period: "/月",
      description: "适合每日剪片、需要更高生成额度的重度用户。",
      features: [
        proGenerationsLabel,
        "包含免费版全部功能",
        "B-Roll 叠加",
        "字幕模板",
        "平台导出预设",
        "优先处理队列",
        "新功能抢先体验",
      ],
      cta: "升级到 Pro",
      ctaHref: "",
      highlighted: true,
      isUnlimited: proLimit === 0,
    },
  ];
}

const STEPS = [
  {
    num: "01",
    title: "粘贴链接或上传文件",
    description:
      "粘贴任意 YouTube 链接，或拖放本地视频文件。",
    icon: Youtube,
  },
  {
    num: "02",
    title: "AI 挑出高光",
    description:
      "转写、传播力评分与片段检测，找出最值得剪的时刻。",
    icon: Wand2,
  },
  {
    num: "03",
    title: "导出并发布",
    description:
      "获得竖屏、带字幕、人脸跟踪的成片，各平台直接可用。",
    icon: Share2,
  },
];

export default function LandingPage() {
  const [scrolled, setScrolled] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const authEnabled = !isLandingOnlyModeEnabled;

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* ─── NAV ─── */}
      <nav
        className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
          scrolled
            ? "bg-background/80 backdrop-blur-xl border-b shadow-sm"
            : "bg-transparent"
        }`}
      >
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5 group">
            <Image
              src="/logo.png"
              alt="SupoClip"
              width={24}
              height={24}
              className="rounded-lg transition-transform group-hover:scale-105"
            />
            <span
              className="text-lg font-bold tracking-tight"
              style={{
                fontFamily:
                  "var(--font-syne), var(--font-geist-sans), system-ui",
              }}
            >
              SupoClip
            </span>
          </Link>

          <div className="hidden md:flex items-center gap-8">
            <a
              href="#how-it-works"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              如何使用
            </a>
            <a
              href="#features"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              功能
            </a>
            <a
              href="#pricing"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              定价
            </a>
            <a
              href="#open-source"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              开源
            </a>
          </div>

          {/* Desktop auth buttons */}
          <div className="hidden md:flex items-center gap-3">
            {authEnabled ? (
              <>
                <Link href="/sign-in">
                  <Button variant="ghost" size="sm">
                    登录
                  </Button>
                </Link>
                <Link href="/sign-up">
                  <Button size="sm">开始使用</Button>
                </Link>
              </>
            ) : (
              <a href={HOSTED_APP_URL} target="_blank" rel="noopener noreferrer">
                <Button size="sm">
                  打开托管版
                  <ExternalLink className="w-3.5 h-3.5" />
                </Button>
              </a>
            )}
          </div>

          {/* Mobile hamburger */}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setMobileNavOpen(!mobileNavOpen)}
            className="md:hidden p-2"
            aria-label="切换菜单"
          >
            {mobileNavOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </Button>
        </div>

        {/* Mobile nav dropdown */}
        {mobileNavOpen && (
          <div className="md:hidden border-t bg-background/95 backdrop-blur-xl">
            <div className="max-w-6xl mx-auto px-6 py-4 space-y-1">
              <a
                href="#how-it-works"
                onClick={() => setMobileNavOpen(false)}
                className="block rounded-lg px-3 py-2.5 text-sm text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
              >
                如何使用
              </a>
              <a
                href="#features"
                onClick={() => setMobileNavOpen(false)}
                className="block rounded-lg px-3 py-2.5 text-sm text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
              >
                功能
              </a>
              <a
                href="#pricing"
                onClick={() => setMobileNavOpen(false)}
                className="block rounded-lg px-3 py-2.5 text-sm text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
              >
                定价
              </a>
              <a
                href="#open-source"
                onClick={() => setMobileNavOpen(false)}
                className="block rounded-lg px-3 py-2.5 text-sm text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
              >
                开源
              </a>
              <Separator className="my-2" />
              <div className="flex flex-col gap-2 px-3 pt-1">
                {authEnabled ? (
                  <>
                    <Link href="/sign-in" onClick={() => setMobileNavOpen(false)}>
                      <Button variant="outline" size="sm" className="w-full">
                        登录
                      </Button>
                    </Link>
                    <Link href="/sign-up" onClick={() => setMobileNavOpen(false)}>
                      <Button size="sm" className="w-full">开始使用</Button>
                    </Link>
                  </>
                ) : (
                  <a href={HOSTED_APP_URL} target="_blank" rel="noopener noreferrer">
                    <Button size="sm" className="w-full">
                      打开托管版
                      <ExternalLink className="w-3.5 h-3.5" />
                    </Button>
                  </a>
                )}
              </div>
            </div>
          </div>
        )}
      </nav>

      {/* ─── HERO ─── */}
      <section className="relative pt-32 pb-20 md:pt-40 md:pb-28 overflow-hidden">
        {/* Subtle background pattern */}
        <div
          className="absolute inset-0 opacity-[0.02]"
          style={{
            backgroundImage:
              "radial-gradient(circle at 1px 1px, currentColor 1px, transparent 0)",
            backgroundSize: "32px 32px",
          }}
        />

        <div className="relative max-w-6xl mx-auto px-6">
          <div className="grid lg:grid-cols-2 gap-16 lg:gap-20 items-center">
            {/* Left: Text */}
            <div>
              <Badge
                variant="secondary"
                className="mb-6 gap-2"
                style={{ animation: "landing-fade-in-up 0.6s ease-out both" }}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                开源且可自托管
              </Badge>

              <h1
                className="text-4xl sm:text-5xl lg:text-[3.5rem] font-extrabold leading-[1.08] tracking-tight text-foreground mb-6"
                style={{
                  fontFamily:
                    "var(--font-syne), var(--font-geist-sans), system-ui",
                  animation: "landing-fade-in-up 0.6s ease-out 0.1s both",
                }}
              >
                长视频
                <br />
                剪成爆款短片
              </h1>

              <p
                className="text-base sm:text-lg text-muted-foreground leading-relaxed max-w-lg mb-10"
                style={{
                  animation: "landing-fade-in-up 0.6s ease-out 0.2s both",
                }}
              >
                AI 驱动的剪片：自动转写、传播力评分、竖屏裁切、逐字同步字幕，并导出各平台就绪的短片。
              </p>

              <div
                className="flex flex-wrap gap-3 mb-10"
                style={{
                  animation: "landing-fade-in-up 0.6s ease-out 0.3s both",
                }}
              >
                {authEnabled ? (
                  <Link href="/sign-up">
                    <Button size="lg" className="px-8 h-12 text-sm">
                      开始剪片
                      <ArrowRight className="w-4 h-4" />
                    </Button>
                  </Link>
                ) : (
                  <a href={HOSTED_APP_URL} target="_blank" rel="noopener noreferrer">
                    <Button size="lg" className="px-8 h-12 text-sm">
                      使用托管版
                      <ExternalLink className="w-4 h-4" />
                    </Button>
                  </a>
                )}
                <a
                  href="https://github.com/FujiwaraChoki/supoclip"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <Button variant="outline" size="lg" className="px-8 h-12 text-sm">
                    <Github className="w-4 h-4" />
                    查看源码
                  </Button>
                </a>
              </div>

              <div
                className="flex flex-wrap gap-x-6 gap-y-2 text-xs text-muted-foreground"
                style={{
                  animation: "landing-fade-in-up 0.6s ease-out 0.4s both",
                }}
              >
                {[
                  { icon: ScanFace, label: "9:16 自动裁切" },
                  { icon: Type, label: "逐字同步字幕" },
                  { icon: Target, label: "传播力评分" },
                ].map(({ icon: Icon, label }) => (
                  <div key={label} className="flex items-center gap-1.5">
                    <Icon className="w-3.5 h-3.5" />
                    {label}
                  </div>
                ))}
              </div>
            </div>

            {/* Right: Visual */}
            <div
              className="relative flex justify-center lg:justify-end"
              style={{ animation: "landing-fade-in-up 0.8s ease-out 0.3s both" }}
            >
              <HeroVisual />
            </div>
          </div>
        </div>

        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 hidden md:block">
          <ChevronDown className="w-5 h-5 text-muted-foreground/30 animate-bounce" />
        </div>
      </section>

      <Separator />

      {/* ─── HOW IT WORKS ─── */}
      <section id="how-it-works" className="py-20 md:py-28 bg-muted/40">
        <div className="max-w-6xl mx-auto px-6">
          <ScrollReveal className="text-center mb-14">
            <p className="text-xs font-semibold tracking-[0.2em] uppercase text-muted-foreground mb-3">
              如何使用
            </p>
            <h2
              className="text-3xl sm:text-4xl font-bold tracking-tight"
              style={{
                fontFamily:
                  "var(--font-syne), var(--font-geist-sans), system-ui",
              }}
            >
              三步完成，省心省力
            </h2>
          </ScrollReveal>

          <div className="grid md:grid-cols-3 gap-6">
            {STEPS.map((step, i) => (
              <ScrollReveal key={step.num} delay={i * 0.1}>
                <Card className="h-full py-0 gap-0 hover:shadow-md transition-shadow duration-300">
                  <CardContent className="p-8">
                    <span
                      className="text-6xl font-black leading-none block mb-6 text-muted-foreground/25 select-none"
                      style={{ fontFamily: "var(--font-syne), system-ui" }}
                    >
                      {step.num}
                    </span>
                    <div className="w-10 h-10 rounded-xl bg-secondary flex items-center justify-center mb-5">
                      <step.icon className="w-5 h-5 text-foreground" />
                    </div>
                    <h3
                      className="text-lg font-semibold mb-2"
                      style={{ fontFamily: "var(--font-syne), system-ui" }}
                    >
                      {step.title}
                    </h3>
                    <p className="text-sm text-muted-foreground leading-relaxed">
                      {step.description}
                    </p>
                  </CardContent>
                </Card>
              </ScrollReveal>
            ))}
          </div>
        </div>
      </section>

      <Separator />

      {/* ─── FEATURES ─── */}
      <section id="features" className="py-20 md:py-28">
        <div className="max-w-6xl mx-auto px-6">
          <ScrollReveal className="text-center mb-14">
            <p className="text-xs font-semibold tracking-[0.2em] uppercase text-muted-foreground mb-3">
              功能
            </p>
            <h2
              className="text-3xl sm:text-4xl font-bold tracking-tight mb-4"
              style={{
                fontFamily:
                  "var(--font-syne), var(--font-geist-sans), system-ui",
              }}
            >
              做爆款所需的全部能力
            </h2>
            <p className="text-sm text-muted-foreground max-w-md mx-auto">
              专业级剪片流程，每一步都有 AI 加持。
            </p>
          </ScrollReveal>

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {FEATURES.map((feature, i) => (
              <ScrollReveal key={feature.title} delay={i * 0.07}>
                <Card className="h-full py-0 gap-0 hover:shadow-md transition-all duration-300 hover:-translate-y-1">
                  <CardContent className="p-6">
                    <div className="w-10 h-10 rounded-xl bg-secondary flex items-center justify-center mb-4">
                      <feature.icon className="w-5 h-5 text-foreground" />
                    </div>
                    <h3 className="font-semibold mb-2">{feature.title}</h3>
                    <p className="text-sm text-muted-foreground leading-relaxed">
                      {feature.description}
                    </p>
                  </CardContent>
                </Card>
              </ScrollReveal>
            ))}
          </div>
        </div>
      </section>

      <Separator />

      {/* ─── PRICING ─── */}
      <section id="pricing" className="relative py-20 md:py-28 bg-muted/40 overflow-hidden">
        {/* Decorative background grain */}
        <div
          className="absolute inset-0 opacity-[0.03] pointer-events-none"
          style={{
            backgroundImage:
              "radial-gradient(circle at 2px 2px, currentColor 0.5px, transparent 0)",
            backgroundSize: "24px 24px",
          }}
        />

        <div className="relative max-w-5xl mx-auto px-6">
          <ScrollReveal className="text-center mb-16">
            <p className="text-xs font-semibold tracking-[0.2em] uppercase text-muted-foreground mb-3">
              定价
            </p>
            <h2
              className="text-3xl sm:text-4xl font-bold tracking-tight mb-4"
              style={{
                fontFamily:
                  "var(--font-syne), var(--font-geist-sans), system-ui",
              }}
            >
              简单透明，没有套路
            </h2>
            <p className="text-sm text-muted-foreground max-w-md mx-auto">
              免费起步，需要更强能力时再升级。自托管用户永久免费使用全部功能。
            </p>
          </ScrollReveal>

          <div className="grid md:grid-cols-2 gap-6 max-w-3xl mx-auto items-start">
            {getPlans().map((plan, i) => (
              <ScrollReveal key={plan.name} delay={i * 0.12}>
                <Card
                  className={`relative py-0 gap-0 transition-all duration-300 hover:shadow-lg ${
                    plan.highlighted
                      ? "bg-primary text-primary-foreground border-primary shadow-xl md:-mt-4 md:mb-4"
                      : "hover:-translate-y-1"
                  }`}
                >
                  {plan.highlighted && (
                    <div className="absolute -top-3.5 left-1/2 -translate-x-1/2">
                      <Badge className="bg-foreground text-background border-0 shadow-md gap-1.5 px-3 py-1">
                        <Zap className="w-3 h-3" />
                        最受欢迎
                      </Badge>
                    </div>
                  )}

                  <CardContent className="p-8">
                    <div className="mb-6">
                      <h3
                        className="text-lg font-semibold mb-1"
                        style={{ fontFamily: "var(--font-syne), system-ui" }}
                      >
                        {plan.name}
                      </h3>
                      <p
                        className={`text-sm ${
                          plan.highlighted
                            ? "text-primary-foreground/70"
                            : "text-muted-foreground"
                        }`}
                      >
                        {plan.description}
                      </p>
                    </div>

                    <div className="flex items-baseline gap-1 mb-8">
                      <span
                        className="text-5xl font-extrabold tracking-tight"
                        style={{ fontFamily: "var(--font-syne), system-ui" }}
                      >
                        {plan.price}
                      </span>
                      <span
                        className={`text-sm ${
                          plan.highlighted
                            ? "text-primary-foreground/60"
                            : "text-muted-foreground"
                        }`}
                      >
                        {plan.period}
                      </span>
                    </div>

                    <ul className="space-y-3 mb-8">
                      {plan.features.map((feature) => (
                        <li key={feature} className="flex items-start gap-3 text-sm">
                          <Check
                            className={`w-4 h-4 mt-0.5 shrink-0 ${
                              plan.highlighted
                                ? "text-primary-foreground/80"
                                : "text-muted-foreground"
                            }`}
                          />
                          <span
                            className={
                              plan.highlighted
                                ? "text-primary-foreground/90"
                                : ""
                            }
                          >
                            {plan.isUnlimited && feature.includes("无限") ? (
                              <span className="flex items-center gap-1.5 font-medium">
                                <Infinity className="w-3.5 h-3.5" />
                                {feature}
                              </span>
                            ) : (
                              feature
                            )}
                          </span>
                        </li>
                      ))}
                    </ul>

                    {plan.ctaHref ? (
                      <a
                        href={plan.ctaHref}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        <Button
                          className="w-full h-11 text-sm"
                          variant="outline"
                          size="lg"
                        >
                          <Github className="w-4 h-4" />
                          {plan.cta}
                          <ExternalLink className="w-3.5 h-3.5 opacity-50" />
                        </Button>
                      </a>
                    ) : authEnabled ? (
                      <Link href="/sign-up">
                        <Button
                          className={`w-full h-11 text-sm ${
                            plan.highlighted
                              ? "bg-primary-foreground text-primary hover:bg-primary-foreground/90"
                              : ""
                          }`}
                          variant={plan.highlighted ? "secondary" : "default"}
                          size="lg"
                        >
                          {plan.cta}
                          <ArrowRight className="w-4 h-4" />
                        </Button>
                      </Link>
                    ) : (
                      <a
                        href={HOSTED_APP_URL}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        <Button
                          className={`w-full h-11 text-sm ${
                            plan.highlighted
                              ? "bg-primary-foreground text-primary hover:bg-primary-foreground/90"
                              : ""
                          }`}
                          variant={plan.highlighted ? "secondary" : "default"}
                          size="lg"
                        >
                          使用托管版
                          <ExternalLink className="w-4 h-4" />
                        </Button>
                      </a>
                    )}
                  </CardContent>
                </Card>
              </ScrollReveal>
            ))}
          </div>

          <ScrollReveal delay={0.3}>
            <p className="text-center text-xs text-muted-foreground mt-10 max-w-md mx-auto">
              自托管？全部功能免费且无限制。{" "}
              <a
                href="#open-source"
                className="underline underline-offset-2 hover:text-foreground transition-colors"
              >
                查看部署说明
              </a>
              。
            </p>
          </ScrollReveal>
        </div>
      </section>

      <Separator />

      {/* ─── OPEN SOURCE ─── */}
      <section id="open-source" className="py-20 md:py-28 bg-muted/40">
        <div className="max-w-3xl mx-auto px-6">
          <ScrollReveal className="text-center mb-10">
            <Badge variant="outline" className="mb-6 gap-1.5">
              <Github className="w-3.5 h-3.5" />
              AGPL-3.0 开源许可
            </Badge>
            <h2
              className="text-3xl sm:text-4xl font-bold tracking-tight mb-4"
              style={{ fontFamily: "var(--font-syne), system-ui" }}
            >
              公开开发，社区共建
            </h2>
            <p className="text-sm text-muted-foreground max-w-lg mx-auto">
              完全开源。可在自有环境自托管、贡献功能，或 Fork 后定制属于你的版本。
            </p>
          </ScrollReveal>

          <ScrollReveal delay={0.1}>
            <Card className="py-0 gap-0">
              <CardContent className="p-6 md:p-8">
                <p className="text-xs font-medium text-muted-foreground mb-3">
                  本地开发：配置 Postgres / Redis 后按脚本提示启动三个进程：
                </p>
                <div className="bg-primary text-primary-foreground rounded-lg p-5 font-mono text-sm leading-loose overflow-x-auto">
                  <div>
                    <span className="opacity-50">$</span>{" "}
                    git clone{" "}
                    <span className="opacity-40">
                      https://github.com/FujiwaraChoki/supoclip
                    </span>
                  </div>
                  <div>
                    <span className="opacity-50">$</span>{" "}
                    cd{" "}
                    <span className="opacity-40">supoclip</span>
                  </div>
                  <div>
                    <span className="opacity-50">$</span> cp .env.example .env
                  </div>
                  <div>
                    <span className="opacity-50">$</span> ./start.sh
                  </div>
                </div>

                <div className="flex flex-wrap gap-3 mt-6">
                  <a
                    href="https://github.com/FujiwaraChoki/supoclip"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <Button>
                      <Github className="w-4 h-4" />
                      在 GitHub 查看
                      <ExternalLink className="w-3.5 h-3.5 opacity-50" />
                    </Button>
                  </a>
                  {authEnabled ? (
                    <Link href="/sign-up">
                      <Button variant="outline">
                        试用托管版
                        <ArrowRight className="w-4 h-4" />
                      </Button>
                    </Link>
                  ) : (
                    <a href={HOSTED_APP_URL} target="_blank" rel="noopener noreferrer">
                      <Button variant="outline">
                        打开托管版
                        <ExternalLink className="w-4 h-4" />
                      </Button>
                    </a>
                  )}
                </div>
              </CardContent>
            </Card>
          </ScrollReveal>
        </div>
      </section>

      <Separator />

      {/* ─── FINAL CTA ─── */}
      <section className="py-20 md:py-28">
        <ScrollReveal className="max-w-2xl mx-auto px-6 text-center">
          <h2
            className="text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight mb-6"
            style={{ fontFamily: "var(--font-syne), system-ui" }}
          >
            准备好剪第一条了吗？
          </h2>
          <p className="text-base text-muted-foreground mb-8">
            把下一条长视频做成让人停不下来的短片。免费、开源，无需信用卡。
          </p>
          {authEnabled ? (
            <Link href="/sign-up">
              <Button size="lg" className="px-10 h-12 text-sm">
                免费开始使用
                <ArrowRight className="w-4 h-4" />
              </Button>
            </Link>
          ) : (
            <a href={HOSTED_APP_URL} target="_blank" rel="noopener noreferrer">
              <Button size="lg" className="px-10 h-12 text-sm">
                打开托管版
                <ExternalLink className="w-4 h-4" />
              </Button>
            </a>
          )}
        </ScrollReveal>
      </section>


      {/* ─── FOOTER ─── */}
      <footer className="border-t py-8 px-6">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Image
              src="/logo.png"
              alt="SupoClip"
              width={24}
              height={24}
              className="rounded-md"
            />
            <span
              className="text-sm font-semibold"
              style={{ fontFamily: "var(--font-syne), system-ui" }}
            >
              SupoClip
            </span>
          </div>
          <div className="flex items-center gap-6 text-xs text-muted-foreground">
            <a
              href="https://github.com/FujiwaraChoki/supoclip"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-foreground transition-colors"
            >
              GitHub
            </a>
            <span>AGPL-3.0</span>
            <span>&copy; {new Date().getFullYear()}</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

/* ─── Hero Visual ─── */
function HeroVisual() {
  return (
    <div className="relative w-full max-w-md">
      <Card className="py-0 gap-0 overflow-hidden shadow-xl border-border/60">
        <CardContent className="p-5">
          {/* Wide video frame */}
          <div
            className="relative w-full rounded-lg overflow-hidden mb-4 bg-muted"
            style={{ aspectRatio: "16/9" }}
          >
            {/* Gradient simulating video content */}
            <div
              className="absolute inset-0 bg-gradient-to-br from-stone-200 via-stone-100 to-stone-200"
            />

            {/* Subtle grid overlay */}
            <div
              className="absolute inset-0 opacity-[0.06]"
              style={{
                backgroundImage:
                  "linear-gradient(currentColor 1px, transparent 1px), linear-gradient(90deg, currentColor 1px, transparent 1px)",
                backgroundSize: "20px 20px",
              }}
            />

            {/* Play button */}
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-12 h-12 rounded-full bg-background/80 backdrop-blur-sm flex items-center justify-center shadow-lg">
                <Play className="w-5 h-5 text-foreground ml-0.5" />
              </div>
            </div>

            {/* Scanning line */}
            <div
              className="absolute top-0 bottom-0 w-0.5 bg-foreground/50 landing-scan-line"
              style={{
                boxShadow: "0 0 12px rgba(0,0,0,0.15)",
                animation: "landing-scan-line 3s ease-in-out infinite",
              }}
            />

            {/* Detected clip regions */}
            {[
              { left: "8%", score: 92, delay: 0 },
              { left: "38%", score: 87, delay: 0.15 },
              { left: "68%", score: 78, delay: 0.3 },
            ].map((clip, i) => (
              <div
                key={i}
                className="absolute top-[8%] bottom-[8%] w-[22%] rounded-md border-2 bg-foreground/[0.03]"
                style={{
                  left: clip.left,
                  animation: `landing-clip-pulse 2.5s ease-in-out ${clip.delay}s infinite`,
                }}
              >
                <Badge className="absolute -top-3 left-1/2 -translate-x-1/2 text-[10px] px-1.5 py-0 h-5">
                  {clip.score}%
                </Badge>
              </div>
            ))}

            {/* Timeline bar */}
            <div className="absolute bottom-2 left-3 right-3 h-1 rounded-full overflow-hidden bg-foreground/10">
              <div className="h-full w-[65%] rounded-full bg-foreground/20" />
              {[15, 42, 73].map((pos, i) => (
                <div
                  key={i}
                  className="absolute top-1/2 -translate-y-1/2 w-1 h-2.5 rounded-full bg-foreground/40"
                  style={{ left: `${pos}%` }}
                />
              ))}
            </div>
          </div>

          {/* Scissors divider */}
          <div className="flex items-center gap-2 mb-4">
            <div className="flex-1 h-px bg-border" />
            <Scissors className="w-4 h-4 text-muted-foreground rotate-90" />
            <div className="flex-1 h-px bg-border" />
          </div>

          {/* Extracted vertical clips */}
          <div className="flex gap-2.5 justify-center">
            {[
              {
                bg: "linear-gradient(135deg, #e8e5e0, #d6d3cd)",
                score: 92,
                label: "开场钩子",
              },
              {
                bg: "linear-gradient(135deg, #dfe0e4, #cdd0d6)",
                score: 87,
                label: "核心观点",
              },
              {
                bg: "linear-gradient(135deg, #e4e2df, #d3d0cb)",
                score: 78,
                label: "结尾号召",
              },
            ].map((clip, i) => (
              <div
                key={i}
                className="relative flex-1 rounded-lg overflow-hidden border shadow-sm"
                style={{
                  aspectRatio: "9/16",
                  background: clip.bg,
                  animation: `landing-float ${2.5 + i * 0.3}s ease-in-out ${
                    i * 0.2
                  }s infinite`,
                }}
              >
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="w-6 h-6 rounded-full bg-background/70 flex items-center justify-center shadow-sm">
                    <Play className="w-3 h-3 text-foreground ml-px" />
                  </div>
                </div>
                <div className="absolute bottom-1.5 left-1 right-1">
                  <div className="text-[7px] text-center font-medium py-0.5 px-1 rounded bg-primary text-primary-foreground">
                    {clip.label}
                  </div>
                </div>
                <Badge className="absolute top-1 right-1 text-[8px] px-1 py-0 h-4">
                  {clip.score}
                </Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Decorative blur spots */}
      <div className="absolute -top-8 -right-8 w-32 h-32 rounded-full bg-muted/80 blur-3xl -z-10" />
      <div className="absolute -bottom-8 -left-8 w-24 h-24 rounded-full bg-muted/60 blur-2xl -z-10" />
    </div>
  );
}
