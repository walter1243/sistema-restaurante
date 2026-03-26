// @ts-nocheck
import React, { useEffect, useState } from 'react';
import { Text, View } from 'react-native';

const API_BASE = 'https://sistema-restaurante-api.onrender.com';

type Cotacao = {
  distancia_metros?: number;
  duracao_segundos?: number;
  zona?: string | null;
  taxa_final?: number;
};

export default function LogisticaMapMobile({ slug = 'solar', lat, lon }: { slug?: string; lat: number; lon: number }) {
  const [cotacao, setCotacao] = useState<Cotacao | null>(null);
  const [erro, setErro] = useState('');

  useEffect(() => {
    fetch(`${API_BASE}/api/public/logistica/${encodeURIComponent(slug)}/cotar-frete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lat, lon }),
    })
      .then((r) => r.json())
      .then((d) => {
        if (!d?.ok) throw new Error(d?.detail || 'Falha ao cotar frete');
        setCotacao(d);
      })
      .catch((e) => setErro(String(e?.message || 'Erro ao cotar frete')));
  }, [slug, lat, lon]);

  return (
    <View style={{ backgroundColor: '#0f172a', padding: 14, borderRadius: 12 }}>
      <Text style={{ color: '#e2e8f0', fontWeight: '700', fontSize: 16 }}>Logística FoodOS</Text>
      {erro ? <Text style={{ color: '#fca5a5', marginTop: 6 }}>{erro}</Text> : null}
      {cotacao ? (
        <>
          <Text style={{ color: '#cbd5e1', marginTop: 8 }}>Distância real: {Math.round(Number(cotacao.distancia_metros || 0))} m</Text>
          <Text style={{ color: '#cbd5e1' }}>Tempo estimado: {Math.round(Number(cotacao.duracao_segundos || 0) / 60)} min</Text>
          <Text style={{ color: '#cbd5e1' }}>Zona: {cotacao.zona || 'fora de zona'}</Text>
          <Text style={{ color: '#86efac', fontWeight: '700' }}>Taxa: R$ {Number(cotacao.taxa_final || 0).toFixed(2)}</Text>
        </>
      ) : null}
    </View>
  );
}
