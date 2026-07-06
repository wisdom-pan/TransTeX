import Navbar from '@/components/Navbar'
import Hero from '@/components/Hero'
import UploadArea from '@/components/UploadArea'
import Features from '@/components/Features'

export default function Home() {
  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-50 to-white">
      <Navbar />
      <div className="container mx-auto px-4 pt-8 pb-16">
        <Hero />
        <UploadArea />
        <Features />
      </div>
    </main>
  )
}
