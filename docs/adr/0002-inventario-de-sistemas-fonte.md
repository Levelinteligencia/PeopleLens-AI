# ADR-0002: Inventário de sistemas-fonte e implementação em duas ondas

- **Status:** Aceita
- **Data:** 2026-09-11
- **Decisão relacionada:** D2 (Technical Design v0.3)
- **Fase:** F0 para a declaração, F2 para a onda 1

## Contexto

A Especificação usa `source_system` em quase todas as tabelas e exige
reconciliação entre sistemas na seção 26, mas não enumera quais sistemas
existem. Sem esse inventário não há como projetar a verdade (ADR-0001), nem
como escrever os checks de reconciliação, nem como dar causa aos defeitos de
formato e de identidade.

Ao mesmo tempo, cada sistema custa um módulo de projeção, um perfil de
corrupção e um conjunto de checks. Declarar doze e implementar doze antes do
primeiro resultado visível atrasaria demais a primeira demonstração.

## Decisão

Os **12 sistemas ficam declarados** em `config/sources.yaml` desde a F0, com
vigência, formato, encoding, formato de data, chave de identidade e defeitos
que carregam. O modelo de dados não muda quando a cobertura crescer.

A **implementação acontece em duas ondas**:

- **Onda 1 (F2):** `HRIS_LEGACY`, `HRIS_CORE`, `PAYROLL_BR`, `ATS_CLOUD`,
  `VIVAMARKET_LEGACY`. Cinco sistemas que já sustentam a migração de 2019 e a
  aquisição de 2022, ou seja, os dois incidentes que geram a maior parte dos
  defeitos.
- **Onda 2 (após F5):** `PAYROLL_LATAM`, `ATS_LEGACY`, `ORGCHART`, `LMS`,
  `ENGAGE`, `COMP_PLAN`, `COMPRAFACIL_ERP`.

## Alternativas consideradas

1. **Três sistemas (HRIS, Payroll, ATS).** Suficiente para um pipeline,
   insuficiente para a narrativa: sem sistema legado não há migração, sem
   sistema de aquisição não há a história de 2022 e 2024.
2. **Cinco sistemas em onda única, sem declarar os demais.** Descartada porque
   o modelo mudaria quando os outros entrassem, e mudança de modelo depois da
   F6 é cara.
3. **Doze sistemas implementados de uma vez.** Cobertura completa, resultado
   visível tarde demais.

## Consequências

**Positivas**

- O esquema e os contratos nascem completos; a cobertura cresce sem refatorar.
- A onda 1 já entrega os dois incidentes mais ricos do dataset.
- `config/sources.yaml` funciona como documentação do universo, legível sem
  abrir código.

**Negativas**

- Durante a onda 1 alguns KPIs ficam sem fonte, por exemplo engajamento e
  aprendizagem. Isso precisa ser tratado como "indisponível", não como zero,
  o que na prática antecipa o comportamento de recusa do sistema.

**Riscos e mitigação**

- *Risco:* a onda 2 nunca acontecer por falta de tempo. *Mitigação:* a onda 1
  foi escolhida para ser autossuficiente como demonstração; a onda 2 amplia,
  não viabiliza.

## Referências

- Technical Design v0.3, seção 3
- Especificação do Universo v1.0, seções 24 e 26
- `config/sources.yaml`
