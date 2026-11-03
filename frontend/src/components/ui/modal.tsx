"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { X, AlertTriangle, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  description?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  maxWidth?: "sm" | "md" | "lg" | "xl";
  className?: string;
}

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  description,
  children,
  footer,
  maxWidth = "md",
  className,
}) => {
  const dialogRef = React.useRef<HTMLDivElement>(null);
  const previousFocusRef = React.useRef<HTMLElement | null>(null);

  const generatedTitleId = React.useId();
  const generatedDescId = React.useId();
  const titleId = title ? generatedTitleId : undefined;
  const descId = description ? generatedDescId : undefined;

  // Manage focus restoration & initial dialog focus
  React.useEffect(() => {
    if (isOpen) {
      previousFocusRef.current = document.activeElement as HTMLElement | null;
      document.body.style.overflow = "hidden";

      const timer = setTimeout(() => {
        if (dialogRef.current) {
          const focusable = dialogRef.current.querySelector<HTMLElement>(
            'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
          );
          if (focusable) {
            focusable.focus();
          } else {
            dialogRef.current.focus();
          }
        }
      }, 50);

      return () => clearTimeout(timer);
    } else {
      document.body.style.overflow = "unset";
      if (previousFocusRef.current && typeof previousFocusRef.current.focus === "function") {
        previousFocusRef.current.focus();
      }
    }
  }, [isOpen]);

  // Focus trap & Escape key listener
  React.useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }

      if (e.key === "Tab" && dialogRef.current) {
        const focusables = dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
        if (focusables.length === 0) return;

        const first = focusables[0];
        const last = focusables[focusables.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const maxWidthClass = {
    sm: "max-w-sm",
    md: "max-w-md",
    lg: "max-w-lg",
    xl: "max-w-2xl",
  }[maxWidth];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4">
      {/* Accessible Backdrop */}
      <div
        className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs transition-opacity animate-in fade-in duration-150"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Modal Dialog Surface */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        tabIndex={-1}
        className={cn(
          "relative w-full rounded-2xl bg-white shadow-2xl border border-slate-200/80 z-10 overflow-hidden flex flex-col max-h-[calc(100vh-2.5rem)] animate-in fade-in zoom-in-95 duration-150 outline-none",
          maxWidthClass,
          className
        )}
      >
        {/* Header */}
        {(title || description) && (
          <div className="shrink-0 flex items-start justify-between p-5 sm:p-6 pb-4 border-b border-slate-100 bg-slate-50/40">
            <div>
              {title && (
                <h3 id={titleId} className="text-base sm:text-lg font-bold text-header leading-snug">
                  {title}
                </h3>
              )}
              {description && (
                <p id={descId} className="text-xs text-slate-500 mt-1 leading-normal">
                  {description}
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={onClose}
              className="text-slate-400 hover:text-slate-700 rounded-lg p-1.5 hover:bg-slate-100 transition-colors ml-3 shrink-0"
              aria-label="Close dialog"
            >
              <X className="w-4 h-4 sm:w-5 sm:h-5" />
            </button>
          </div>
        )}

        {/* Scrollable Body Container */}
        <div className="p-5 sm:p-6 text-sm text-slate-700 overflow-y-auto flex-1 min-h-0 space-y-4">
          {children}
        </div>

        {/* Footer */}
        {footer && (
          <div className="shrink-0 flex items-center justify-end gap-2.5 px-5 sm:px-6 py-3.5 bg-slate-50/80 border-t border-slate-100">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
};

export interface ConfirmModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void | Promise<void>;
  title: string;
  description?: string;
  message?: string;
  consequenceNotice?: string;
  confirmText?: string;
  confirmLabel?: string;
  cancelText?: string;
  cancelLabel?: string;
  variant?: "danger" | "warning" | "default";
  confirmVariant?: "danger" | "warning" | "default";
  isLoading?: boolean;
  icon?: React.ReactNode;
  children?: React.ReactNode;
}

export const ConfirmModal: React.FC<ConfirmModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  title,
  description,
  message,
  consequenceNotice,
  confirmText,
  confirmLabel,
  cancelText,
  cancelLabel,
  variant,
  confirmVariant,
  isLoading = false,
  icon,
  children,
}) => {
  const resolvedDesc = description || message || "";
  const resolvedConfirm = confirmLabel || confirmText || "Confirm";
  const resolvedCancel = cancelLabel || cancelText || "Cancel";
  const resolvedVariant = confirmVariant || variant || "danger";

  const isDanger = resolvedVariant === "danger";
  const isWarning = resolvedVariant === "warning";

  const defaultIcon = isDanger ? (
    <div className="w-10 h-10 rounded-xl bg-rose-50 text-rose-600 border border-rose-200/60 flex items-center justify-center shrink-0">
      <AlertTriangle className="w-5 h-5" />
    </div>
  ) : isWarning ? (
    <div className="w-10 h-10 rounded-xl bg-amber-50 text-amber-600 border border-amber-200/60 flex items-center justify-center shrink-0">
      <AlertCircle className="w-5 h-5" />
    </div>
  ) : null;

  return (
    <Modal
      isOpen={isOpen}
      onClose={isLoading ? () => {} : onClose}
      maxWidth="md"
      footer={
        <>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={isLoading}
            onClick={onClose}
            className="text-xs"
          >
            {resolvedCancel}
          </Button>
          <Button
            type="button"
            variant={isDanger ? "destructive" : "primary"}
            size="sm"
            isLoading={isLoading}
            disabled={isLoading}
            onClick={onConfirm}
            className="text-xs shadow-xs"
          >
            {resolvedConfirm}
          </Button>
        </>
      }
    >
      <div className="space-y-3.5">
        <div className="flex items-start gap-3.5">
          {icon || defaultIcon}
          <div className="space-y-1 flex-1">
            <h4 className="text-sm font-bold text-header leading-tight">{title}</h4>
            {resolvedDesc && <p className="text-xs text-slate-600 leading-relaxed">{resolvedDesc}</p>}
          </div>
        </div>

        {consequenceNotice && (
          <div className="p-3 bg-slate-50 border border-slate-200/80 rounded-xl text-xs text-slate-600 space-y-1">
            <span className="font-semibold text-slate-700 block text-[11px] uppercase tracking-wider">
              Expected Outcome & Safety
            </span>
            <p className="text-[11px] text-slate-500 leading-relaxed">{consequenceNotice}</p>
          </div>
        )}

        {children}
      </div>
    </Modal>
  );
};
