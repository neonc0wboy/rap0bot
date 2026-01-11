document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById('rapForm');
  const loading = document.getElementById('loading');
  const result = document.getElementById('result');
  const error = document.getElementById('error');
  const generateBtn = document.getElementById('generateBtn');
  const randomSeedBtn = document.getElementById('randomSeedBtn');
  const seedWordsInput = document.getElementById('seedWordsInput');
  const statusEl = document.getElementById('status');
  const progressEl = document.getElementById('progress');
  const progressBar = document.getElementById('progressBar');
  const playTTSBtn = document.getElementById('playTTSBtn');

  function setStatus(text) { statusEl.textContent = text; }
  function setProgress(percent) { progressEl.classList.add('show'); progressBar.style.width = `${percent}%`; }
  function resetProgress() { progressEl.classList.remove('show'); progressBar.style.width = '0%'; statusEl.textContent = ''; }

  async function fetchWithRetry(url, options = {}, retries = 3, timeout = 30000) {
    for (let attempt = 1; attempt <= retries; attempt++) {
      try {
        setStatus(`🔄 Попытка ${attempt}...`);
        setProgress(Math.round((attempt - 1) / retries * 100));
        const controller = new AbortController();
        const id = setTimeout(() => controller.abort(), timeout);
        const response = await fetch(url, { ...options, signal: controller.signal });
        clearTimeout(id);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        setProgress(100);
        setStatus('✅ Успех');
        return response;
      } catch (err) {
        setStatus(`❌ Попытка ${attempt} не удалась: ${err.message}`);
        if (attempt === retries) throw new Error("Все попытки исчерпаны. Сервер недоступен или слишком долго отвечает.");
        await new Promise(r => setTimeout(r, 1200 * attempt));
      }
    }
  }

  randomSeedBtn.addEventListener('click', async () => {
    loading.classList.add('show');
    error.classList.remove('show');
    result.classList.remove('show');
    try {
      const selectedLang = document.querySelector('input[name="seedLang"]:checked');
      if (!selectedLang) throw new Error("Язык не выбран");
      const lang = selectedLang.value;
      const response = await fetchWithRetry(`/generate_random_seed?lang=${encodeURIComponent(lang)}`, { method: 'GET' }, 3, 15000);
      const data = await response.json();
      seedWordsInput.value = data.seed_words || '';
      resetProgress();
    } catch (err) {
      error.textContent = `❌ Ошибка генерации seed-слов: ${err.message}`;
      error.classList.add('show');
    } finally {
      loading.classList.remove('show');
    }
  });

  async function playRapTTS(rapText, lang) {
    try {
      setStatus('🔊 Генерируем аудио...');
      const resp = await fetch('/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rap_text: rapText, lang: lang })
      });
      if (!resp.ok) throw new Error('TTS request failed');
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.onended = () => { URL.revokeObjectURL(url); setStatus(''); };
      audio.play();
      setStatus('▶️ Воспроизведение');
    } catch (err) {
      console.error('TTS error:', err);
      setStatus('');
      error.textContent = `❌ Ошибка TTS: ${err.message}`;
      error.classList.add('show');
    }
  }

  playTTSBtn.addEventListener('click', () => {
    const rapText = document.getElementById('rapText').textContent;
    if (!rapText) return;
    const lang = document.querySelector('input[name="seedLang"]:checked').value || 'ru';
    playRapTTS(rapText, lang);
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const artistName = document.getElementById('artistName').value || 'Anonymous';
    const inviteCode = document.getElementById('inviteCode').value;
    const seedWords = seedWordsInput.value;
    const selectedLang = document.querySelector('input[name="seedLang"]:checked');
    if (!selectedLang) {
      error.textContent = "❌ Ошибка: язык не выбран";
      error.classList.add('show');
      return;
    }
    const lang = selectedLang.value;

    const punchAmount = document.getElementById('punchAmount') ? document.getElementById('punchAmount').value : 3;
    const lyricsLove = document.getElementById('lyricsLove') ? document.getElementById('lyricsLove').checked : false;
    const storytelling = document.getElementById('storytelling') ? document.getElementById('storytelling').checked : false;
    const melancholy = document.getElementById('melancholy') ? document.getElementById('melancholy').checked : false;
    const oneVsAll = document.getElementById('oneVsAll') ? document.getElementById('oneVsAll').checked : false;
    const mood = document.getElementById('mood') ? document.getElementById('mood').value : 3;

    loading.classList.add('show');
    result.classList.remove('show');
    error.classList.remove('show');
    generateBtn.disabled = true;
    playTTSBtn.disabled = true;

    try {
      const params = new URLSearchParams({
        artist_name: artistName,
        invite_code: inviteCode,
        seed_words: seedWords,
        lang: lang,
        punch_amount: punchAmount,
        lyrics_love: lyricsLove ? "1" : "0",
        storytelling: storytelling ? "1" : "0",
        melancholy: melancholy ? "1" : "0",
        one_vs_all: oneVsAll ? "1" : "0",
        mood: mood
      });

      const response = await fetchWithRetry(`/generate_rap?${params.toString()}`, { method: 'GET' }, 3, 45000);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Ошибка при генерации');

      document.getElementById('seedWords').textContent = data.seed_words || '';
      document.getElementById('rapText').textContent = data.rap_text || '';
      result.classList.add('show');
      resetProgress();

      playTTSBtn.disabled = false;
      // Автовоспроизведение TTS после генерации
      playRapTTS(data.rap_text || '', lang);
    } catch (err) {
      error.textContent = `❌ Ошибка: ${err.message}`;
      error.classList.add('show');
    } finally {
      loading.classList.remove('show');
      generateBtn.disabled = false;
    }
  });
});
