import { FormEvent, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const apiUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

function App() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState(sessionStorage.getItem("access_token") ?? "");
  const [message, setMessage] = useState("Ingrese con una cuenta habilitada por ADMIN.");

  async function login(event: FormEvent) {
    event.preventDefault();
    const response = await fetch(`${apiUrl}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!response.ok) {
      setMessage("No fue posible iniciar sesion. Verifique sus credenciales.");
      return;
    }
    const token = await response.json() as { access_token: string };
    sessionStorage.setItem("access_token", token.access_token);
    setToken(token.access_token);
    setMessage("Sesion iniciada. Puede imprimir formularios de transicion FT.");
  }

  async function printForm(module: string) {
    const response = await fetch(`${apiUrl}/exportar?modulo=${module}`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) {
      setMessage("No fue posible obtener el formulario.");
      return;
    }
    const url = URL.createObjectURL(await response.blob());
    window.open(url, "_blank", "noopener");
  }

  return <main>
    <section className="panel">
      <p className="eyebrow">F0 · Fundamentos</p>
      <h1>Control de Proceso</h1>
      <p className="subtitle">Preparacion de Pasta</p>
      {!token ? <form onSubmit={login}>
        <label>Usuario<input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required /></label>
        <label>Contrasena<input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" required /></label>
        <button type="submit">Iniciar sesion</button>
      </form> : <section className="forms">
        <h2>Formularios de transicion</h2>
        <p>Imprima y complete fecha, hora, turno y responsable. La carga posterior conserva esos datos originales.</p>
        {["m1", "m2", "m3", "m6", "m10"].map((module) => <button key={module} onClick={() => printForm(module)}>Imprimir {module.toUpperCase()}</button>)}
      </section>}
      <p className="message" role="status">{message}</p>
    </section>
  </main>;
}

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
createRoot(document.getElementById("root")!).render(<App />);
