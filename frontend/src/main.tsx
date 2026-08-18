// React entrypoint: mounts <App /> into #root and pulls in global styles.
// TODO: wrap in <React.StrictMode> and any global providers (query client, etc.)

import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles/globals.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
