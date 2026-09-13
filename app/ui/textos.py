"""Textos da interface, em PT-BR e EN-US.

**Aqui não se traduz resultado.** O que este módulo carrega é rótulo de tela:
título, botão, cabeçalho de tabela, nome de bloco. Valor, KPI, período, escopo,
trust e nível vêm do envelope, e são neutros de idioma.

A resposta narrativa do agente é produzida em português pelo `render.py` do
core, que a UI não toca. Em EN-US ela aparece na seção técnica, rotulada como
original, e nunca reescrita: reescrever a resposta de uma camada governada seria
a UI opinando sobre o que a governança já decidiu.

Membro de dimensão também não se traduz. "Customer Service" é "Customer
Service" nos dois idiomas, porque é um valor governado e não um rótulo.
"""
from __future__ import annotations

PT = "pt-BR"
EN = "en-US"
IDIOMAS = (PT, EN)

T: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------- cabeçalho
    "titulo":            {PT: "PeopleLens AI", EN: "PeopleLens AI"},
    "subtitulo":         {PT: "People Analytics governado, movido a IA",
                          EN: "Governed People Analytics, powered by AI"},
    "idioma":            {PT: "Idioma", EN: "Language"},

    # --------------------------------------------------------------- entrada
    "pergunta":          {PT: "Faça uma pergunta de People Analytics",
                          EN: "Ask a People Analytics question"},
    "placeholder":       {PT: "Qual foi o turnover de Customer Service em 2025?",
                          EN: "What was turnover for Customer Service in 2025?"},
    "perguntar":         {PT: "Perguntar", EN: "Ask"},
    "exemplos":          {PT: "Exemplos", EN: "Examples"},
    "pensando":          {PT: "Consultando a camada governada…",
                          EN: "Querying the governed layer…"},

    # -------------------------------------------------------------- resposta
    "escopo":            {PT: "Escopo", EN: "Scope"},
    "periodo":           {PT: "Período", EN: "Period"},
    "populacao":         {PT: "População", EN: "Population"},
    "toda_a_empresa":    {PT: "Toda a empresa", EN: "Company-wide"},
    "confianca":         {PT: "Confiança", EN: "Trust"},
    "nivel":             {PT: "Nível de resposta", EN: "Response level"},
    "teto_de":           {PT: "teto de", EN: "ceiling from"},
    "ressalvas":         {PT: "Ressalvas", EN: "Caveats"},
    "resposta_agente":   {PT: "Resposta do agente", EN: "Agent response"},

    # ------------------------------------------------------------ comparação
    "comparacao":        {PT: "Comparação", EN: "Comparison"},
    "periodo_atual":     {PT: "Período atual", EN: "Current period"},
    "periodo_base":      {PT: "Comparado com", EN: "Compared with"},
    "variacao":          {PT: "Variação", EN: "Change"},
    "variacao_relativa": {PT: "Variação relativa", EN: "Relative change"},
    "direcao":           {PT: "Direção", EN: "Direction"},
    "SUBIU":             {PT: "Subiu", EN: "Increased"},
    "CAIU":              {PT: "Caiu", EN: "Decreased"},
    "ESTAVEL":           {PT: "Estável", EN: "Stable"},
    "nota_associacao":   {PT: "Variação observada no tempo. É associação, "
                              "não relação de causa.",
                          EN: "Variation observed over time. This is "
                              "association, not causation."},

    # --------------------------------------------------------------- ranking
    "ranking":           {PT: "Quebra por dimensão", EN: "Breakdown"},
    "col_valor":         {PT: "Valor", EN: "Value"},
    "col_populacao":     {PT: "População", EN: "Population"},
    "col_situacao":      {PT: "Situação", EN: "Status"},
    "publicado":         {PT: "Publicado", EN: "Published"},
    "suprimido":         {PT: "Suprimido", EN: "Suppressed"},
    "linhas_suprimidas": {PT: "{n} de {total} linhas suprimidas por privacidade",
                          EN: "{n} of {total} rows suppressed for privacy"},
    "suprimido_aviso":   {PT: "Linhas suprimidas não são omissão de dado: são "
                              "proteção de privacidade. O valor delas não é "
                              "reconstruído em lugar nenhum.",
                          EN: "Suppressed rows are not missing data: they are "
                              "privacy protection. Their values are not "
                              "reconstructed anywhere."},

    # ---------------------------------------------------------------- recusas
    "smart_refusal":     {PT: "Não posso responder com segurança",
                          EN: "I cannot answer this with confidence"},
    "recusa_governada":  {PT: "Recusa governada", EN: "Governed refusal"},
    "supressao":         {PT: "Suprimido por privacidade",
                          EN: "Suppressed for privacy"},
    "parcial":           {PT: "Resposta parcial", EN: "Partial answer"},
    "o_que_falta":       {PT: "O que precisa ser esclarecido",
                          EN: "What needs to be clarified"},
    "opcoes_validas":    {PT: "Opções válidas", EN: "Valid options"},
    "sem_reformular":    {PT: "A pergunta não foi reformulada nem repetida. "
                              "Recusa é um resultado, não uma falha.",
                          EN: "The question was not rephrased or retried. "
                              "A refusal is a result, not a failure."},

    # ------------------------------------------------------ como foi calculado
    "como_calculado":    {PT: "Como foi calculado?",
                          EN: "How was this calculated?"},
    "definicao":         {PT: "Definição de negócio", EN: "Business definition"},
    "formula":           {PT: "Fórmula declarada", EN: "Declared formula"},
    "exclusoes":         {PT: "Exclusões", EN: "Exclusions"},
    "filtros_contrato":  {PT: "Filtros fixos do contrato",
                          EN: "Contract fixed filters"},
    "minimo_n":          {PT: "Mínimo de população", EN: "Minimum population"},
    "governanca":        {PT: "Governança", EN: "Governance"},
    "owner":             {PT: "Responsável", EN: "Owner"},
    "status":            {PT: "Status", EN: "Status"},
    "cobertura":         {PT: "Cobertura", EN: "Coverage"},
    "verificacao":       {PT: "Cobertura de verificação",
                          EN: "Check coverage"},
    "linhagem":          {PT: "Linhagem", EN: "Lineage"},
    "sem_linhagem":      {PT: "Linhagem não disponível para este resultado.",
                          EN: "Lineage not available for this result."},

    # ------------------------------------------------------------- execução
    "detalhes":          {PT: "Detalhes da execução", EN: "Execution details"},
    "interpretador":     {PT: "Interpretador", EN: "Interpreter"},
    "modelo":            {PT: "Modelo", EN: "Model"},
    "orcamento":         {PT: "Orçamento de LLM", EN: "LLM budget"},
    "fallback_ativo":    {PT: "Fallback acionado", EN: "Fallback triggered"},
    "stop_reason":       {PT: "Motivo de parada", EN: "Stop reason"},
    "duracao":           {PT: "Duração", EN: "Duration"},
    "chamadas":          {PT: "Chamadas ao MCP", EN: "MCP calls"},
    "plano":             {PT: "Plano", EN: "Plan"},
    "intent":            {PT: "Intent", EN: "Intent"},
    "texto_original":    {PT: "Resposta original do agente (PT-BR)",
                          EN: "Original agent response (PT-BR)"},
    "nota_idioma":       {PT: "",
                          EN: "The agent composes its narrative in Portuguese. "
                              "The executive fields above are built from the "
                              "governed envelope, not translated from it."},

    # ---------------------------------------------------------------- rodapé
    "rodape":            {PT: "Dados sintéticos. Empresa fictícia. "
                              "Não representa estatística real de nenhuma "
                              "empresa ou país.",
                          EN: "Synthetic data. Fictional company. Does not "
                              "represent real statistics of any company or "
                              "country."},
    "sem_credencial":    {PT: "Sem credencial de LLM: o interpretador "
                              "determinístico está respondendo.",
                          EN: "No LLM credential: the deterministic "
                              "interpreter is answering."},
}

# Os quatro cenários demonstráveis, nos dois idiomas. São perguntas, e por isso
# **não** são traduções uma da outra: cada uma é escrita no seu idioma.
EXEMPLOS: dict[str, list[str]] = {
    PT: [
        "Qual foi o turnover de Customer Service em 2025?",
        "Qual área teve o maior turnover em 2025?",
        "Como o turnover de Customer Service mudou entre 2024 e 2025?",
        "Qual foi o turnover de Tecnologia no segundo trimestre de 2026?",
    ],
    EN: [
        "What was turnover for Customer Service in 2025?",
        "Which area had the highest turnover in 2025?",
        "How did turnover for Customer Service change between 2024 and 2025?",
        "What was turnover for Tecnologia in the second quarter of 2026?",
    ],
}


def t(chave: str, idioma: str, **fmt) -> str:
    """Rótulo de tela. Chave desconhecida aparece como a própria chave."""
    texto = T.get(chave, {}).get(idioma, chave)
    return texto.format(**fmt) if fmt else texto
