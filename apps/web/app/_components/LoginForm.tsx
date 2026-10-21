"use client";

import { useState } from "react";
import { supabase } from "../_lib/supabase";

export function LoginForm() {
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setInfo("");
    const auth = supabase().auth;
    const { data, error: err } =
      mode === "signin"
        ? await auth.signInWithPassword({ email, password })
        : await auth.signUp({ email, password });
    setBusy(false);
    if (err) setError(err.message);
    else if (mode === "signup" && !data.session) setInfo("Kiểm tra email để xác nhận tài khoản.");
  }

  return (
    <form className="card login" onSubmit={submit}>
      <h2>{mode === "signin" ? "Đăng nhập" : "Tạo tài khoản"}</h2>
      <label>
        Email
        <input
          type="email"
          name="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </label>
      <label>
        Mật khẩu
        <input
          type="password"
          name="password"
          autoComplete={mode === "signin" ? "current-password" : "new-password"}
          required
          minLength={6}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      {error && <p className="error">{error}</p>}
      {info && <p className="muted">{info}</p>}
      <button type="submit" disabled={busy}>
        {mode === "signin" ? "Đăng nhập" : "Đăng ký"}
      </button>
      <button
        type="button"
        className="link"
        onClick={() => setMode(mode === "signin" ? "signup" : "signin")}
      >
        {mode === "signin" ? "Chưa có tài khoản? Đăng ký" : "Đã có tài khoản? Đăng nhập"}
      </button>
    </form>
  );
}
