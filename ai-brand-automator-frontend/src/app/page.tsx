'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

export default function Home() {
  const router = useRouter();
  const [isLoaded, setIsLoaded] = useState(false);

  useEffect(() => {
    // Check if user is authenticated
    const token = localStorage.getItem('access_token');
    if (token) {
      router.push('/chat');
      return; // Don't set loaded if redirecting
    }
    // Use requestAnimationFrame to avoid synchronous setState in effect
    requestAnimationFrame(() => setIsLoaded(true));
  }, [router]);

  return (
    <div className="min-h-screen bg-brand-midnight overflow-hidden">
      {/* Animated gradient mesh background */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-1/2 -left-1/2 w-full h-full bg-gradient-to-br from-brand-ghost/20 via-transparent to-transparent rounded-full blur-3xl animate-pulse" style={{ animationDuration: '8s' }} />
        <div className="absolute -bottom-1/2 -right-1/2 w-full h-full bg-gradient-to-tl from-brand-electric/10 via-transparent to-transparent rounded-full blur-3xl animate-pulse" style={{ animationDuration: '10s', animationDelay: '2s' }} />
        <div className="absolute top-1/4 right-1/4 w-96 h-96 bg-brand-mint/5 rounded-full blur-3xl animate-pulse" style={{ animationDuration: '12s', animationDelay: '4s' }} />
      </div>

      {/* Grid pattern overlay */}
      <div 
        className="fixed inset-0 opacity-[0.02] pointer-events-none"
        style={{
          backgroundImage: `linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)`,
          backgroundSize: '50px 50px'
        }}
      />

      {/* Header */}
      <header className={`relative z-50 px-4 sm:px-6 py-4 transition-all duration-700 ${isLoaded ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-4'}`}>
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row justify-between items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-electric to-brand-ghost flex items-center justify-center">
              <svg className="w-6 h-6 text-brand-midnight" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <h1 className="text-xl sm:text-2xl font-heading font-bold text-white">AI Brand Automator</h1>
          </div>
          <nav className="hidden md:flex items-center gap-8">
            <a href="#features" className="text-brand-silver/70 hover:text-white transition-colors text-sm">Features</a>
            <a href="#platforms" className="text-brand-silver/70 hover:text-white transition-colors text-sm">Platforms</a>
            <a href="#testimonials" className="text-brand-silver/70 hover:text-white transition-colors text-sm">Testimonials</a>
            <a href="#pricing" className="text-brand-silver/70 hover:text-white transition-colors text-sm">Pricing</a>
          </nav>
          <div className="flex items-center gap-3">
            <Link
              href="/auth/login"
              className="text-brand-silver hover:text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              Sign In
            </Link>
            <Link
              href="/auth/register"
              className="relative group bg-gradient-to-r from-brand-electric to-brand-ghost text-brand-midnight font-bold px-5 py-2.5 rounded-lg text-sm transition-all hover:shadow-[0_0_30px_rgba(0,245,255,0.4)] hover:-translate-y-0.5"
            >
              <span className="relative z-10">Get Started Free</span>
            </Link>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <main className="relative z-10">
        <section className="max-w-7xl mx-auto px-4 sm:px-6 pt-12 pb-20 sm:pt-20 sm:pb-32">
          <div className={`text-center transition-all duration-1000 delay-200 ${isLoaded ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}>
            {/* Badge */}
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/5 border border-white/10 mb-8">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-mint opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-brand-mint"></span>
              </span>
              <span className="text-sm text-brand-silver/80">Trusted by 10,000+ brands worldwide</span>
            </div>

            {/* Main headline */}
            <h1 className="text-4xl sm:text-5xl md:text-7xl font-heading font-bold text-white mb-6 leading-tight">
              Build Your Brand
              <span className="block mt-2 bg-gradient-to-r from-brand-electric via-brand-ghost to-brand-mint bg-clip-text text-transparent animate-gradient">
                on Autopilot
              </span>
            </h1>
            
            <p className="text-lg sm:text-xl text-brand-silver/70 mb-10 max-w-2xl mx-auto font-body leading-relaxed">
              AI-powered brand management that handles your social media, content creation, and analytics. 
              <span className="text-white font-medium"> Save 20+ hours per week.</span>
            </p>

            {/* CTA Buttons */}
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16">
              <Link
                href="/auth/register"
                className="group relative inline-flex items-center gap-2 bg-white text-brand-midnight font-bold px-8 py-4 rounded-xl text-lg transition-all hover:shadow-[0_0_40px_rgba(255,255,255,0.2)] hover:-translate-y-1"
              >
                Start Free Trial
                <svg className="w-5 h-5 group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                </svg>
              </Link>
              <Link
                href="#demo"
                className="group inline-flex items-center gap-2 text-brand-silver hover:text-white px-6 py-4 rounded-xl text-lg transition-colors"
              >
                <div className="w-12 h-12 rounded-full bg-white/10 flex items-center justify-center group-hover:bg-white/20 transition-colors">
                  <svg className="w-5 h-5 ml-0.5" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M8 5v14l11-7z" />
                  </svg>
                </div>
                Watch Demo
              </Link>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 max-w-4xl mx-auto">
              {[
                { value: '10K+', label: 'Active Users' },
                { value: '50M+', label: 'Posts Scheduled' },
                { value: '99.9%', label: 'Uptime' },
                { value: '4.9★', label: 'User Rating' },
              ].map((stat, i) => (
                <div 
                  key={i} 
                  className={`glass-card p-4 sm:p-6 transition-all duration-700 hover:border-brand-electric/30 ${isLoaded ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}
                  style={{ transitionDelay: `${400 + i * 100}ms` }}
                >
                  <div className="text-2xl sm:text-3xl font-bold text-white mb-1">{stat.value}</div>
                  <div className="text-xs sm:text-sm text-brand-silver/60">{stat.label}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Brand Equity Calculator CTA — inside hero for maximum visibility */}
          <div className={`mt-12 sm:mt-16 max-w-3xl mx-auto transition-all duration-1000 delay-400 ${isLoaded ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}>
            <Link href="/brand-equity" className="group block glass-card p-6 sm:p-8 text-center border-brand-electric/30 hover:border-brand-electric/60 transition-all hover:shadow-[0_0_40px_rgba(0,245,255,0.15)]">
              <div className="flex items-center justify-center gap-3 mb-3">
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-brand-mint/10 border border-brand-mint/20 text-xs text-brand-mint font-medium">
                  <span className="w-1.5 h-1.5 bg-brand-mint rounded-full animate-pulse" />
                  Free Tool
                </span>
              </div>
              <h3 className="text-xl sm:text-2xl font-heading font-bold text-white mb-2">
                Know Your Brand&apos;s True Value
              </h3>
              <p className="text-sm text-brand-silver/60 mb-5 max-w-lg mx-auto">
                Get an instant ISO 20671 brand equity score with competitor analysis — powered by Claude AI. No sign up required.
              </p>
              <span className="inline-flex items-center gap-2 bg-gradient-to-r from-brand-electric to-brand-ghost text-brand-midnight font-bold px-8 py-3.5 rounded-xl transition-all group-hover:shadow-[0_0_30px_rgba(0,245,255,0.4)] group-hover:-translate-y-0.5">
                Calculate Brand Equity — Free
                <svg className="w-5 h-5 group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                </svg>
              </span>
            </Link>
          </div>

          {/* Hero Image/Dashboard Preview */}
          <div className={`mt-16 sm:mt-24 relative transition-all duration-1000 delay-500 ${isLoaded ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-12'}`}>
            <div className="absolute inset-0 bg-gradient-to-t from-brand-midnight via-transparent to-transparent z-10 pointer-events-none" />
            <div className="relative rounded-2xl overflow-hidden border border-white/10 shadow-2xl shadow-brand-ghost/10">
              <div className="bg-gradient-to-br from-white/[0.08] to-white/[0.02] p-2">
                {/* Browser chrome */}
                <div className="flex items-center gap-2 px-3 py-2 border-b border-white/10">
                  <div className="flex gap-1.5">
                    <div className="w-3 h-3 rounded-full bg-red-500/80" />
                    <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
                    <div className="w-3 h-3 rounded-full bg-green-500/80" />
                  </div>
                  <div className="flex-1 flex justify-center">
                    <div className="px-4 py-1 rounded-md bg-white/5 text-xs text-brand-silver/50">app.aibrandautomator.com</div>
                  </div>
                </div>
                {/* Dashboard mockup */}
                <div className="aspect-[16/9] bg-brand-midnight/50 rounded-lg p-6 grid grid-cols-3 gap-4">
                  <div className="col-span-2 space-y-4">
                    <div className="h-8 w-48 bg-white/10 rounded-lg animate-pulse" />
                    <div className="grid grid-cols-3 gap-3">
                      {[1,2,3].map(i => (
                        <div key={i} className="glass-card p-4 space-y-2">
                          <div className="h-4 w-16 bg-white/10 rounded" />
                          <div className="h-6 w-20 bg-brand-electric/20 rounded" />
                        </div>
                      ))}
                    </div>
                    <div className="glass-card p-4 h-32 flex items-center justify-center">
                      <div className="w-full h-20 bg-gradient-to-r from-brand-electric/20 via-brand-ghost/20 to-brand-mint/20 rounded-lg" />
                    </div>
                  </div>
                  <div className="space-y-4">
                    <div className="glass-card p-4 space-y-3">
                      <div className="h-4 w-24 bg-white/10 rounded" />
                      {[1,2,3].map(i => (
                        <div key={i} className="flex items-center gap-2">
                          <div className="w-8 h-8 rounded-full bg-brand-ghost/20" />
                          <div className="flex-1 h-3 bg-white/10 rounded" />
                        </div>
                      ))}
                    </div>
                    <div className="glass-card p-4">
                      <div className="h-4 w-20 bg-white/10 rounded mb-3" />
                      <div className="space-y-2">
                        {[1,2].map(i => (
                          <div key={i} className="h-10 bg-white/5 rounded-lg" />
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            {/* Floating elements */}
            <div className="absolute -left-4 top-1/4 glass-card p-4 hidden lg:flex items-center gap-3 animate-float">
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-pink-500 to-purple-600 flex items-center justify-center">
                <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069z"/>
                </svg>
              </div>
              <div>
                <div className="text-sm font-medium text-white">+2.4K followers</div>
                <div className="text-xs text-brand-silver/60">This week</div>
              </div>
            </div>
            <div className="absolute -right-4 top-1/3 glass-card p-4 hidden lg:flex items-center gap-3 animate-float" style={{ animationDelay: '1s' }}>
              <div className="w-10 h-10 rounded-full bg-[#1DA1F2] flex items-center justify-center">
                <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
                </svg>
              </div>
              <div>
                <div className="text-sm font-medium text-white">156 posts</div>
                <div className="text-xs text-brand-silver/60">Scheduled</div>
              </div>
            </div>
          </div>
        </section>

        {/* Platform Integrations */}
        <section id="platforms" className="py-16 border-y border-white/5">
          <div className="max-w-7xl mx-auto px-4 sm:px-6">
            <p className="text-center text-sm text-brand-silver/50 mb-8">SEAMLESSLY INTEGRATES WITH YOUR FAVORITE PLATFORMS</p>
            <div className="flex flex-wrap items-center justify-center gap-8 sm:gap-16 opacity-60 hover:opacity-100 transition-opacity">
              {[
                { name: 'LinkedIn', color: '#0A66C2', icon: 'M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z' },
                { name: 'Twitter/X', color: '#000', icon: 'M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z' },
                { name: 'Instagram', color: '#E4405F', icon: 'M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z' },
                { name: 'Facebook', color: '#1877F2', icon: 'M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z' },
                { name: 'TikTok', color: '#000', icon: 'M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z' },
              ].map((platform, i) => (
                <div key={i} className="group flex items-center gap-2 cursor-pointer">
                  <svg className="w-6 h-6 text-brand-silver group-hover:text-white transition-colors" fill="currentColor" viewBox="0 0 24 24">
                    <path d={platform.icon} />
                  </svg>
                  <span className="text-sm text-brand-silver/70 group-hover:text-white transition-colors hidden sm:inline">{platform.name}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Features Bento Grid */}
        <section id="features" className="py-20 sm:py-32">
          <div className="max-w-7xl mx-auto px-4 sm:px-6">
            <div className="text-center mb-16">
              <h2 className="text-3xl sm:text-4xl md:text-5xl font-heading font-bold text-white mb-4">
                Everything You Need to
                <span className="block text-brand-electric">Dominate Social Media</span>
              </h2>
              <p className="text-lg text-brand-silver/70 max-w-2xl mx-auto">
                Powerful features that work together to save you time and grow your brand.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6">
              {/* Large feature card */}
              <div className="lg:col-span-2 lg:row-span-2 glass-card p-8 group hover:border-brand-electric/30 transition-all relative overflow-hidden">
                <div className="absolute top-0 right-0 w-64 h-64 bg-gradient-to-bl from-brand-electric/10 to-transparent rounded-full blur-3xl" />
                <div className="relative">
                  <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-brand-electric to-cyan-400 flex items-center justify-center mb-6">
                    <svg className="w-7 h-7 text-brand-midnight" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                    </svg>
                  </div>
                  <h3 className="text-2xl font-heading font-bold text-white mb-3">AI Content Generation</h3>
                  <p className="text-brand-silver/70 mb-6 max-w-md">
                    Generate engaging posts, captions, and hashtags with our advanced AI. Tailored to your brand voice and audience.
                  </p>
                  <div className="glass-card p-4 max-w-sm">
                    <div className="flex items-center gap-3 mb-3">
                      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-ghost to-brand-electric flex items-center justify-center">
                        <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 24 24">
                          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
                        </svg>
                      </div>
                      <span className="text-sm text-white">AI just wrote your next viral post</span>
                    </div>
                    <div className="p-3 bg-white/5 rounded-lg text-sm text-brand-silver/80">
                      &quot;🚀 Exciting news! We just launched our new feature that will change the way you work. Ready to 10x your productivity? Link in bio! #productivity #startup&quot;
                    </div>
                  </div>
                </div>
              </div>

              {/* Feature cards */}
              {[
                {
                  icon: (
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                  ),
                  title: 'Smart Scheduling',
                  description: 'Post at the perfect time for maximum engagement. Our AI learns when your audience is most active.',
                  gradient: 'from-purple-500 to-pink-500'
                },
                {
                  icon: (
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                    </svg>
                  ),
                  title: 'Deep Analytics',
                  description: 'Track growth, engagement, and ROI across all platforms in one beautiful dashboard.',
                  gradient: 'from-green-500 to-emerald-500'
                },
                {
                  icon: (
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                    </svg>
                  ),
                  title: 'Team Collaboration',
                  description: 'Work together with approval workflows, role-based access, and shared content calendars.',
                  gradient: 'from-orange-500 to-amber-500'
                },
                {
                  icon: (
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                    </svg>
                  ),
                  title: 'Real-time Webhooks',
                  description: 'Get instant notifications for comments, mentions, and engagement across all platforms.',
                  gradient: 'from-blue-500 to-cyan-500'
                },
              ].map((feature, i) => (
                <div key={i} className="glass-card p-6 group hover:border-brand-electric/30 transition-all">
                  <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${feature.gradient} flex items-center justify-center mb-4 text-white`}>
                    {feature.icon}
                  </div>
                  <h3 className="text-lg font-heading font-semibold text-white mb-2">{feature.title}</h3>
                  <p className="text-sm text-brand-silver/70">{feature.description}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Testimonials */}
        <section id="testimonials" className="py-20 sm:py-32 bg-gradient-to-b from-transparent via-brand-ghost/5 to-transparent">
          <div className="max-w-7xl mx-auto px-4 sm:px-6">
            <div className="text-center mb-16">
              <h2 className="text-3xl sm:text-4xl font-heading font-bold text-white mb-4">
                Loved by Marketers Worldwide
              </h2>
              <p className="text-lg text-brand-silver/70">See what our users have to say</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {[
                {
                  quote: "AI Brand Automator has completely transformed how we manage our social presence. We've saved 25+ hours per week!",
                  author: "Sarah Chen",
                  role: "Marketing Director",
                  company: "TechFlow Inc.",
                  avatar: "SC"
                },
                {
                  quote: "The AI content generation is incredible. It understands our brand voice perfectly and creates engaging posts every time.",
                  author: "Marcus Johnson",
                  role: "Founder",
                  company: "Growth Labs",
                  avatar: "MJ"
                },
                {
                  quote: "Finally, one tool that handles all our social platforms. The analytics dashboard alone is worth every penny.",
                  author: "Emily Rodriguez",
                  role: "Social Media Manager",
                  company: "Stellar Brands",
                  avatar: "ER"
                },
              ].map((testimonial, i) => (
                <div key={i} className="glass-card p-6 hover:border-brand-electric/30 transition-all">
                  <div className="flex gap-1 mb-4">
                    {[1,2,3,4,5].map(star => (
                      <svg key={star} className="w-5 h-5 text-yellow-400" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                      </svg>
                    ))}
                  </div>
                  <p className="text-brand-silver/80 mb-6 leading-relaxed">&quot;{testimonial.quote}&quot;</p>
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-gradient-to-br from-brand-electric to-brand-ghost flex items-center justify-center text-sm font-bold text-brand-midnight">
                      {testimonial.avatar}
                    </div>
                    <div>
                      <div className="text-sm font-medium text-white">{testimonial.author}</div>
                      <div className="text-xs text-brand-silver/60">{testimonial.role}, {testimonial.company}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Start Free Trial CTA */}
        <section className="py-20 sm:py-32">
          <div className="max-w-4xl mx-auto px-4 sm:px-6 text-center">
            <div className="glass-card p-8 sm:p-12 relative overflow-hidden">
              <div className="absolute inset-0 bg-gradient-to-r from-brand-electric/10 via-brand-ghost/10 to-brand-mint/10" />
              <div className="relative">
                <h2 className="text-3xl sm:text-4xl font-heading font-bold text-white mb-4">
                  Ready to Transform Your Brand?
                </h2>
                <p className="text-lg text-brand-silver/70 mb-8 max-w-xl mx-auto">
                  Join 10,000+ brands already using AI Brand Automator to grow their social presence.
                </p>
                <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                  <Link
                    href="/auth/register"
                    className="group relative inline-flex items-center gap-2 bg-white text-brand-midnight font-bold px-8 py-4 rounded-xl text-lg transition-all hover:shadow-[0_0_40px_rgba(255,255,255,0.2)] hover:-translate-y-1"
                  >
                    Start Your Free Trial
                    <svg className="w-5 h-5 group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                    </svg>
                  </Link>
                </div>
                <p className="mt-4 text-sm text-brand-silver/50">No credit card required • 14-day free trial</p>
              </div>
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="relative z-10 border-t border-white/10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-12">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-8">
            <div className="col-span-2 md:col-span-1">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-electric to-brand-ghost flex items-center justify-center">
                  <svg className="w-4 h-4 text-brand-midnight" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                </div>
                <span className="font-heading font-bold text-white">AI Brand Automator</span>
              </div>
              <p className="text-sm text-brand-silver/60">Automate your brand with the power of AI.</p>
            </div>
            <div>
              <h4 className="font-semibold text-white mb-4">Product</h4>
              <ul className="space-y-2 text-sm text-brand-silver/60">
                <li><a href="#features" className="hover:text-white transition-colors">Features</a></li>
                <li><a href="#pricing" className="hover:text-white transition-colors">Pricing</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Integrations</a></li>
                <li><a href="#" className="hover:text-white transition-colors">API</a></li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold text-white mb-4">Company</h4>
              <ul className="space-y-2 text-sm text-brand-silver/60">
                <li><a href="#" className="hover:text-white transition-colors">About</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Blog</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Careers</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Contact</a></li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold text-white mb-4">Legal</h4>
              <ul className="space-y-2 text-sm text-brand-silver/60">
                <li><a href="#" className="hover:text-white transition-colors">Privacy</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Terms</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Security</a></li>
              </ul>
            </div>
          </div>
          <div className="pt-8 border-t border-white/10 flex flex-col sm:flex-row justify-between items-center gap-4">
            <p className="text-sm text-brand-silver/50">&copy; {new Date().getFullYear()} AI Brand Automator. All rights reserved.</p>
            <div className="flex items-center gap-4">
              {['twitter', 'linkedin', 'instagram'].map(social => (
                <a key={social} href="#" className="w-8 h-8 rounded-full bg-white/5 flex items-center justify-center hover:bg-white/10 transition-colors">
                  <svg className="w-4 h-4 text-brand-silver/60" fill="currentColor" viewBox="0 0 24 24">
                    {social === 'twitter' && <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>}
                    {social === 'linkedin' && <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>}
                    {social === 'instagram' && <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069z"/>}
                  </svg>
                </a>
              ))}
            </div>
          </div>
        </div>
      </footer>

      {/* CSS for animations */}
      <style jsx>{`
        @keyframes gradient {
          0%, 100% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
        }
        .animate-gradient {
          background-size: 200% 200%;
          animation: gradient 3s ease infinite;
        }
        @keyframes float {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(-10px); }
        }
        .animate-float {
          animation: float 3s ease-in-out infinite;
        }
      `}</style>
    </div>
  );
}
