import * as React from "react";
import Image from "next/image";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen flex bg-white font-sans antialiased">
      {/* Left Branding Illustration Section (Visible on lg and up) */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden bg-[#ffecd8] items-center justify-center p-8">
        <div className="relative w-full h-full max-h-[720px] max-w-[600px] flex items-center justify-center">
          <Image
            src="/auth/Login.png"
            alt="Agile Sales & Marketing Auth Portal"
            fill
            className="object-contain"
            priority
          />
        </div>
      </div>

      {/* Right Form Section */}
      <div className="w-full lg:w-1/2 flex flex-col justify-between p-6 sm:p-12 lg:p-16 min-h-screen overflow-y-auto">
        {/* Brand Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Image
              src="/logo.svg"
              alt="Agile"
              width={160}
              height={44}
              className="h-10 w-auto"
              priority
            />
            <span className="hidden sm:inline-block border-l border-slate-200 pl-3 text-xs font-semibold tracking-wider text-slate-500 uppercase">
              Sales & Marketing
            </span>
          </div>
        </div>

        {/* Form Container */}
        <div className="my-auto py-8 flex flex-col items-center justify-center w-full">
          <div className="w-full max-w-md">
            {children}
          </div>
        </div>

        {/* Footer */}
        <div className="pt-6 border-t border-slate-100 flex flex-col sm:flex-row items-center justify-between text-xs text-slate-400 gap-2">
          <span>&copy; {new Date().getFullYear()} Agile Receivables Inc. All rights reserved.</span>
          <div className="flex gap-4">
            <a href="#" className="hover:text-slate-600 transition-colors">Privacy</a>
            <a href="#" className="hover:text-slate-600 transition-colors">Terms</a>
            <a href="#" className="hover:text-slate-600 transition-colors">Security</a>
          </div>
        </div>
      </div>
    </div>
  );
}
