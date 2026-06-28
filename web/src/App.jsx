import { useCallback, useEffect, useState } from "react";
import CharacterPicker from "./components/CharacterPicker.jsx";
import ChatView from "./components/ChatView.jsx";
import { api } from "./api.js";

export default function App() {
  const [personas, setPersonas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);

  const loadPersonas = useCallback(() => {
    setLoading(true);
    setError("");
    api
      .listPersonas()
      .then((data) => setPersonas(Array.isArray(data) ? data : []))
      .catch((e) => setError(e.message || "Could not load characters."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadPersonas();
  }, [loadPersonas]);

  return (
    <div className="app">
      {selected ? (
        <ChatView persona={selected} onBack={() => setSelected(null)} />
      ) : (
        <CharacterPicker
          personas={personas}
          loading={loading}
          error={error}
          onSelect={setSelected}
          onRetry={loadPersonas}
        />
      )}
    </div>
  );
}
