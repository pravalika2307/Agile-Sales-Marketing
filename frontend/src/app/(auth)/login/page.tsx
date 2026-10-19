"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Eye, EyeOff, Loader2, LogIn, AlertCircle, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirectTarget = searchParams.get("redirect") || "/";
  const reason = searchParams.get("reason");

  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [showPassword, setShowPassword] = React.useState(false);
  const [isLoading, setIsLoading] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [successMessage, setSuccessMessage] = React.useState<string | null>(null);

  // Field-level validation errors
  const [fieldErrors, setFieldErrors] = React.useState<{
    email?: string;
    password?: string;
  }>({});

  const validate = (): boolean => {
    const errors: { email?: string; password?: string } = {};

    if (!email.trim()) {
      errors.email = "Email is required.";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      errors.email = "Please enter a valid email address.";
    }

    if (!password) {
      errors.password = "Password is required.";
    } else if (password.length < 8) {
      errors.password = "Password must be at least 8 characters.";
    }

    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (isLoading) return; // Prevent duplicate submissions

    setErrorMessage(null);
    setSuccessMessage(null);

    if (!validate()) {
      return;
    }

    setIsLoading(true);

    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email: email.trim().toLowerCase(),
          password,
        }),
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        const errorDetail =
          data?.detail ||
          data?.error ||
          data?.message ||
          "Authentication failed. Please verify your credentials.";
        setErrorMessage(errorDetail);
        setIsLoading(false);
        return;
      }

      setSuccessMessage("Authentication successful. Redirecting to workspace...");

      // Small delay to allow session cookies to settle before navigation
      setTimeout(() => {
        router.replace(redirectTarget);
        router.refresh();
      }, 400);
    } catch (err: unknown) {
      setErrorMessage("Network connection error. Please verify the server is running.");
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full space-y-6">
      {/* Title & Welcome */}
      <div className="space-y-2 text-left">
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
          Welcome back
        </h1>
        <p className="text-sm text-slate-500">
          Sign in to your Agile Sales & Marketing organization to access campaigns, leads, and outreach workflows.
        </p>
      </div>

      {/* Inactivity Notification */}
      {reason === "inactive" && !errorMessage && (
        <div className="p-3.5 bg-amber-50 border border-amber-200 rounded-lg flex items-center gap-3 text-amber-800 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0 text-amber-600" />
          <span>Your session timed out due to inactivity. Please sign in again.</span>
        </div>
      )}

      {/* Error Alert Banner */}
      {errorMessage && (
        <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-lg flex items-start gap-3 text-rose-800 text-sm animate-in fade-in duration-200">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-rose-600" />
          <div className="flex-1 leading-snug">{errorMessage}</div>
        </div>
      )}

      {/* Success Alert Banner */}
      {successMessage && (
        <div className="p-3.5 bg-emerald-50 border border-emerald-200 rounded-lg flex items-center gap-3 text-emerald-800 text-sm">
          <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600" />
          <span>{successMessage}</span>
        </div>
      )}

      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {/* Email Field */}
        <div className="space-y-1.5 text-left">
          <label
            htmlFor="email"
            className="block text-xs font-semibold text-slate-700 tracking-wide"
          >
            Work Email Address
          </label>
          <Input
            id="email"
            type="email"
            name="email"
            autoComplete="email"
            placeholder="you@agilereceivables.com"
            value={email}
            disabled={isLoading}
            onChange={(e) => {
              setEmail(e.target.value);
              if (fieldErrors.email) setFieldErrors((prev) => ({ ...prev, email: undefined }));
              if (errorMessage) setErrorMessage(null);
            }}
            className={`h-11 bg-slate-50/50 ${
              fieldErrors.email ? "border-rose-400 focus:ring-rose-200" : ""
            }`}
            autoFocus
          />
          {fieldErrors.email && (
            <p className="text-xs text-rose-600 font-medium pl-0.5">{fieldErrors.email}</p>
          )}
        </div>

        {/* Password Field */}
        <div className="space-y-1.5 text-left">
          <div className="flex items-center justify-between">
            <label
              htmlFor="password"
              className="block text-xs font-semibold text-slate-700 tracking-wide"
            >
              Password
            </label>
            <span className="text-xs text-slate-400 cursor-not-allowed">
              Forgot password?
            </span>
          </div>
          <div className="relative">
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              name="password"
              autoComplete="current-password"
              placeholder="••••••••••••"
              value={password}
              disabled={isLoading}
              onChange={(e) => {
                setPassword(e.target.value);
                if (fieldErrors.password) setFieldErrors((prev) => ({ ...prev, password: undefined }));
                if (errorMessage) setErrorMessage(null);
              }}
              className={`h-11 pr-10 bg-slate-50/50 ${
                fieldErrors.password ? "border-rose-400 focus:ring-rose-200" : ""
              }`}
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              tabIndex={-1}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors p-1"
              aria-label={showPassword ? "Hide password" : "Show password"}
            >
              {showPassword ? (
                <EyeOff className="w-4 h-4" />
              ) : (
                <Eye className="w-4 h-4" />
              )}
            </button>
          </div>
          {fieldErrors.password && (
            <p className="text-xs text-rose-600 font-medium pl-0.5">{fieldErrors.password}</p>
          )}
        </div>

        {/* Submit Button */}
        <div className="pt-2">
          <Button
            type="submit"
            disabled={isLoading}
            className="w-full h-11 bg-agile-red hover:bg-[#e04528] text-white font-medium text-sm transition-all shadow-sm active:scale-[0.99] flex items-center justify-center gap-2 cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Signing in...</span>
              </>
            ) : (
              <>
                <LogIn className="w-4 h-4" />
                <span>Sign in to Dashboard</span>
              </>
            )}
          </Button>
        </div>
      </form>

      {/* Security notice */}
      <div className="p-3 bg-slate-50 border border-slate-100 rounded-lg text-center text-xs text-slate-400">
        Protected by secure Argon2id password hashing and encrypted HttpOnly session credentials.
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <React.Suspense
      fallback={
        <div className="flex items-center justify-center min-h-[300px]">
          <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
        </div>
      }
    >
      <LoginForm />
    </React.Suspense>
  );
}
