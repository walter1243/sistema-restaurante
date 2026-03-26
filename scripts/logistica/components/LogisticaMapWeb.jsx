import React, { useEffect, useMemo, useState } from 'react';

const API_BASE = 'https://sistema-restaurante-f87o.onrender.com';

export default function LogisticaMapWeb({ slug = 'solar', destino }) {
  const [config, setConfig] = useState(null);
  const [cotacao, setCotacao] = useState(null);
  const [erro, setErro] = useState('');

  const centro = useMemo(() => config?.centro || { lat: -14.235, lon: -51.925 }, [config]);

  useEffect(() => {
    let ativo = true;
    fetch(`${API_BASE}/api/public/logistica/${encodeURIComponent(slug)}/config-mapa`)
      .then((r) => r.json())
      .then((d) => {
        if (!ativo) return;
        if (!d?.ok) throw new Error(d?.detail || 'Falha ao carregar mapa logístico');
        setConfig(d);
      })
      .catch((e) => {
        if (!ativo) return;
        setErro(String(e?.message || 'Erro ao carregar configuração logística'));
      });
    return () => {
      ativo = false;
    };
  }, [slug]);

  useEffect(() => {
    if (!destino?.lat || !destino?.lon) return;
    fetch(`${API_BASE}/api/public/logistica/${encodeURIComponent(slug)}/cotar-frete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lat: destino.lat, lon: destino.lon }),
    })
      .then((r) => r.json())
      .then((d) => {
        if (!d?.ok) throw new Error(d?.detail || 'Falha ao cotar frete');
        setCotacao(d);
      })
      .catch((e) => setErro(String(e?.message || 'Erro ao cotar frete')));
  }, [slug, destino?.lat, destino?.lon]);

  return (
    <section style={{ background: '#0f172a', color: '#e2e8f0', borderRadius: 12, padding: 16 }}>
      <h3 style={{ marginTop: 0 }}>Mapa Logístico (Maxim Style)</h3>
      {erro ? <p style={{ color: '#fca5a5' }}>{erro}</p> : null}
      <p style={{ margin: '8px 0' }}>
        Centro do restaurante: {Number(centro.lat || 0).toFixed(5)}, {Number(centro.lon || 0).toFixed(5)}
      </p>
      <p style={{ margin: '8px 0' }}>Cor de rota: {config?.rota_cor || '#0052cc'}</p>
      <p style={{ margin: '8px 0' }}>Zonas carregadas: {Array.isArray(config?.zonas) ? config.zonas.length : 0}</p>
      {cotacao ? (
        <div style={{ marginTop: 10, border: '1px solid #334155', borderRadius: 10, padding: 10 }}>
          <div>Distância real: {Math.round(Number(cotacao.distancia_metros || 0))} m</div>
          <div>Duração estimada: {Math.round(Number(cotacao.duracao_segundos || 0) / 60)} min</div>
          <div>Zona: {cotacao.zona || 'fora de zona'}</div>
          <div>Taxa final: R$ {Number(cotacao.taxa_final || 0).toFixed(2)}</div>
        </div>
      ) : null}
      <small style={{ display: 'block', marginTop: 10, color: '#93c5fd' }}>
        Este componente consome APIs do backend sem expor chave de mapa no frontend.
      </small>
    </section>
  );
}
