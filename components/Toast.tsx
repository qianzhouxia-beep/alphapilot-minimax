// Toast notification component for user feedback
"use client";

import { useEffect, useState } from "react";

type ToastType = "success" | "error" | "info" | "warning";

type ToastProps = {
  message: string;
  type?: ToastType;
  duration?: number;
  onClose?: () => void;
};

const toastStyles: Record<ToastType, string> = {
  success: "bg-[rgba(62,230,168,0.12)] text-[#3EE6A8] border-[rgba(62,230,168,0.3)]",
  error: "bg-[rgba(255,93,93,0.12)] text-[#FF5D5D] border-[rgba(255,93,93,0.3)]",
  warning: "bg-[rgba(245,196,81,0.12)] text-[#F5C451] border-[rgba(245,196,81,0.3)]",
  info: "bg-[rgba(77,163,255,0.12)] text-[#4DA3FF] border-[rgba(77,163,255,0.3)]",
};

const toastIcons: Record<ToastType, string> = {
  success: "check_circle",
  error: "error",
  warning: "warning",
  info: "info",
};

export function Toast({ message, type = "info", duration = 3000, onClose }: ToastProps) {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    if (duration > 0) {
      const timer = setTimeout(() => {
        setVisible(false);
        onClose?.();
      }, duration);
      return () => clearTimeout(timer);
    }
  }, [duration, onClose]);

  if (!visible) return null;

  return (
    <div className={`fixed top-4 right-4 z-50 rounded-lg border px-4 py-3 shadow-lg animate-slide-in ${toastStyles[type]}`}>
      <div className="flex items-center gap-3">
        <span className="material-symbols-outlined" style={{ fontSize: 20 }}>
          {toastIcons[type]}
        </span>
        <p className="text-[14px] font-medium">{message}</p>
        <button
          onClick={() => {
            setVisible(false);
            onClose?.();
          }}
          className="ml-2 opacity-70 hover:opacity-100"
        >
          <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
            close
          </span>
        </button>
      </div>
    </div>
  );
}

// Toast hook for easy usage
export function useToast() {
  const [toast, setToast] = useState<ToastProps | null>(null);

  const showToast = (message: string, type: ToastType = "info", duration = 3000) => {
    setToast({ message, type, duration, onClose: () => setToast(null) });
  };

  const ToastComponent = toast ? <Toast {...toast} /> : null;

  return { showToast, ToastComponent };
}
