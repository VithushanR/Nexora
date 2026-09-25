// Renders Google's own Sign-In button (google.accounts.id.renderButton)
// into a plain div once Google Identity Services has initialized.

import { useEffect, useRef } from "react";
import { useAuth } from "./AuthContext";

interface GoogleSignInButtonProps {
  width?: number;
}

export default function GoogleSignInButton({ width = 220 }: GoogleSignInButtonProps) {
  const { scriptReady } = useAuth();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!scriptReady || !containerRef.current || !window.google) return;
    containerRef.current.innerHTML = "";
    window.google.accounts.id.renderButton(containerRef.current, {
      type: "standard",
      theme: "outline",
      size: "large",
      width,
    });
  }, [scriptReady, width]);

  if (!scriptReady) {
    return <p className="text-xs text-slate-400">Loading sign-in…</p>;
  }

  return <div ref={containerRef} />;
}
