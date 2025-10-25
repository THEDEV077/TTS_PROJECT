import React, { useState } from "react";
import axios from "axios";
import "./App.css"; // On garde notre joli CSS

// L'URL de base de ton API.
// Si ton API tourne sur localhost:8000, c'est parfait.
// Sinon, modifie cette ligne.
const API_BASE_URL = "http://localhost:8000";

function App() {
  // --- Les États (Mémoire) ---
  const [text, setText] = useState(
    "Bonjour tout le monde, j'espère que vous allez bien."
  );
  const [voice, setVoice] = useState("af_heart"); // Valeur par défaut de ton API
  const [lang, setLang] = useState("f"); // Valeur par défaut de ton API
  const [speed, setSpeed] = useState(1.0); // Valeur par défaut de ton API

  const [audioUrl, setAudioUrl] = useState(null); // Stockera le lien (ex: /download/kokoro_123.wav)
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null); // Pour afficher les erreurs de l'API

  // --- La Logique (Fonction) ---
  const handleGenerateAudio = async () => {
    setIsLoading(true);
    setAudioUrl(null); // Réinitialise l'ancien audio
    setError(null); // Réinitialise les erreurs

    try {
      // 1. Préparer les données à envoyer
      const payload = {
        text: text,
        voice: voice,
        lang: lang,
        speed: parseFloat(speed), // S'assurer que 'speed' est un nombre
      };

      // 2. Appeler l'API (POST sur /tts)
      // On n'attend plus un 'blob', mais du JSON (comportement par défaut d'Axios)
      const response = await axios.post(`${API_BASE_URL}/tts`, payload);

      // 3. Gérer la réponse JSON
      if (response.data && response.data.success) {
        // Succès ! On stocke le lien relatif
        setAudioUrl(response.data.data.download_url);
      } else {
        // Si success: false ou format inattendu
        setError(response.data.message || "Une erreur inconnue est survenue.");
      }
    } catch (err) {
      // 4. Gérer les erreurs (ex: 422, 500...)
      if (err.response && err.response.data && err.response.data.detail) {
        // C'est une erreur FastAPI (ex: "Texte trop long")
        setError(`Erreur: ${err.response.data.detail}`);
      } else if (err.request) {
        // L'API n'a pas répondu (elle n'est pas lancée ?)
        setError(
          `Erreur de connexion. L'API est-elle lancée sur ${API_BASE_URL} ?`
        );
      } else {
        // Autre erreur
        setError("Une erreur inattendue est survenue.");
      }
      console.error("Erreur lors de la génération :", err);
    } finally {
      setIsLoading(false); // Fin du chargement
    }
  };

  // --- Le Rendu (JSX / HTML) ---
  return (
    <div className="App">
      <h1>Mon Synthétiseur Vocal (Kokoro)</h1>

      {/* Conteneur pour tous les réglages */}
      <div className="form-container">
        {/* Champ de saisie de texte */}
        <label htmlFor="text-input">Texte à synthétiser</label>
        <textarea
          id="text-input"
          rows="5"
          placeholder="Entrez votre texte ici..."
          value={text}
          onChange={(e) => setText(e.target.value)}
        />

        {/* Grille pour les options Voice et Lang */}
        <div className="options-grid">
          <div>
            <label htmlFor="voice-input">Voix (Voice)</label>
            <input
              id="voice-input"
              type="text"
              value={voice}
              onChange={(e) => setVoice(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="lang-input">Langue (Lang)</label>
            <input
              id="lang-input"
              type="text"
              value={lang}
              onChange={(e) => setLang(e.target.value)}
            />
          </div>
        </div>

        {/* Slider pour la vitesse */}
        <label htmlFor="speed-slider">Vitesse (Speed) : {speed}x</label>
        <input
          id="speed-slider"
          type="range"
          min="0.5"
          max="2.0"
          step="0.1"
          value={speed}
          onChange={(e) => setSpeed(e.target.value)}
        />

        {/* Bouton "Générer" */}
        <button onClick={handleGenerateAudio} disabled={isLoading || !text}>
          {isLoading ? "Génération en cours..." : "Générer l'audio"}
        </button>
      </div>

      {/* Affichage de l'erreur (si elle existe) */}
      {error && <div className="error-message">{error}</div>}

      {/* Affichage du résultat (si 'audioUrl' existe) */}
      {audioUrl && (
        <div className="audio-result">
          <h3>Résultat :</h3>

          {/* Le lecteur audio */}
          <audio controls src={`${API_BASE_URL}${audioUrl}`}>
            Votre navigateur ne supporte pas l'élément audio.
          </audio>

          {/* Le lien de téléchargement */}
          <a
            href={`${API_BASE_URL}${audioUrl}`}
            download // Laisse le navigateur choisir le nom (ex: kokoro_123.wav)
          >
            Télécharger le fichier audio
          </a>
        </div>
      )}
    </div>
  );
}

export default App;
