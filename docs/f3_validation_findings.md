# F3: o que o pipeline encontrou

Terceira edição do registro de achados. Mesmo princípio das duas anteriores: os
erros ficam documentados porque uma camada de validação que nunca falhou não
provou nada.

A F3 teve cinco achados. Dois deles mudaram configuração, dois mudaram código, e
um exige decisão da Sam.

---

## Achado 1: a comparação com o gabarito estava comparando execuções diferentes

| | |
|---|---|
| **Sintoma** | desvio de headcount de 7.075.727% entre verdade e pipeline |
| **Severidade** | **crítica**, e pelo mesmo motivo do achado 1 da F2 |

### O que acontecia

A camada de verdade em `data/synthetic/truth/` tinha sido escrita por uma
execução no perfil `dev`, e o RAW em `data/raw/` por uma execução posterior no
perfil `smoke`, disparada pela suíte de testes. Os dois lados existiam, tinham a
forma certa, e descreviam empresas diferentes.

A comparação rodou sem erro e produziu números. Números sem sentido, mas
números: taxas de recuperação de 7%, países divergindo em 42% dos registros.
Todos plausíveis o bastante para não gritar, e todos falsos.

### Por que isso é da mesma família do achado crítico da F2

Os dois corrompem o **gabarito**, não o dado. Na F2 o ledger registrava
corrupção que não existia; aqui o gabarito inteiro era de outro universo. Nos
dois casos, o pipeline seria julgado contra uma referência errada, e a conclusão
sairia errada na direção mais difícil de detectar.

O agravante desta vez: o manifesto já carregava `seed`, `profile`, `scale` e
`config_hash` desde a F1, exatamente para tornar isso verificável. Faltava
alguém conferir. Informação existir não é o mesmo que informação ser usada.

### A correção

`pipeline.check_provenance` compara os manifestos do RAW e da camada de verdade
antes de qualquer coisa. Se `seed`, `profile` ou `scale` divergirem, a
comparação com o gabarito não roda e o relatório diz por quê, em vez de exibir
números inválidos. O status aparece na primeira linha da execução.

---

## Achado 2: um check de integridade referencial acusando 23% de órfãos falsos

| | |
|---|---|
| **Encontrado por** | `DQ_REF_002`, gestor existe no cadastro |
| **Sintoma** | 23,3% de gestores órfãos contra uma taxa injetada de 1,8% |

### O que acontecia

O check comparava `HRIS_LEGACY.GESTOR` contra `HRIS_LEGACY.MATRICULA`, ou seja,
usava **um dataset** como universo de referência. Mas o cadastro legado cobre
apenas quem esteve ativo entre 2016 e 2019, e um gestor pode existir na empresa
sem estar naquele recorte de arquivo.

Resultado: 348 órfãos, dos quais cerca de 24 eram o defeito D09 de verdade e o
resto era artefato do escopo do arquivo.

### Por que a correção não é afrouxar o limiar

Afrouxar o limiar de 3% para 25% faria o check passar e destruiria seu valor: a
partir daí ele nunca detectaria o defeito real. O problema não era o limiar, era
a definição do universo de referência.

**Quando a entidade vive em vários sistemas, a referência de um check de
integridade não pode ser um dataset isolado.** Ela tem que ser o universo de
identidades conformadas, que é justamente o que o `xref_employee_identity`
existe para materializar (ADR-0004).

### A correção

O `xref` passou a ser exposto ao runner como dataset consultável
(`CONFORMED.identity`), e o check aponta para ele. A taxa caiu de 23,3% para
0,99%, que é a ordem de grandeza do defeito injetado, e o check voltou a
detectar o que deveria.

Efeito colateral bom: ficou explícito que a camada de identidade é
pré-requisito da camada de qualidade, e não uma etapa paralela.

---

## Achado 3: datas que o sistema declara e a aritmética não resolve

| | |
|---|---|
| **Sintoma** | 2.122 datas reprovadas como ambíguas na primeira versão |
| **Decisão tomada** | converter pela declaração e tornar a ambiguidade visível |

`01/05/2009` é uma data válida em `%d/%m/%Y` e em `%m/%d/%Y`, e as duas leituras
dão dias diferentes. A primeira versão do parser tratava isso como falha, e
reprovava praticamente toda data brasileira do sistema legado.

Havia três saídas, e nenhuma é obviamente certa:

1. **reprovar** toda data ambígua: honesto e inutilizável, derruba o dataset;
2. **converter em silêncio** pelo formato declarado: usável e desonesto, porque
   esconde que o número depende de uma declaração que pode estar errada;
3. **converter pela declaração e registrar a ambiguidade**: o valor é usável e a
   dependência fica visível.

Ficou a terceira. `sources.yaml` declara o formato de cada sistema, a declaração
vence, e cada valor ganha a marca `__ambiguous`. O check `DQ_VALID_003` conta
quantos valores dependem daquela declaração estar certa, com severidade WARNING.

O que isso protege: no dia em que a onda 2 trouxer o `ATS_LEGACY`, que declara
`%m/%d/%Y`, a mesma string vai ser lida de outro jeito, e o check já existe para
mostrar o tamanho da exposição.

---

## Achado 4: subtração de contagem virando número gigante

| | |
|---|---|
| **Sintoma** | desvio de headcount aparecendo como 7 milhões por cento |
| **Severidade** | baixa em consequência, alta em disfarce |

A contagem de linhas do Polars vem como inteiro **sem sinal**. Subtrair duas
contagens onde a segunda é maior produz underflow silencioso: em vez de um
número negativo, sai um número astronômico.

O sintoma ajudou a encontrar o achado 1, mas os dois são independentes: mesmo com
as execuções alinhadas, qualquer mês em que o pipeline ficasse abaixo da verdade
reportaria um desvio absurdo em vez de um negativo.

Correção de uma linha, cast explícito para inteiro com sinal antes da
subtração. Fica registrado porque é o tipo de erro que passa em revisão de
código: a expressão está certa, o tipo é que não.

---

## Achado 5: o DE/PARA ambíguo estoura o limiar, e isso precisa de decisão

| | |
|---|---|
| **Encontrado por** | `DQ_VALID_006`, job level em domínio corporativo |
| **Situação** | 13,12% de `UNMAPPED` contra um limiar de 10%, severidade CRITICAL |

Este não é um erro, é o desenho funcionando. A escala `N1` a `N7` da VivaMarket
mapeia sem ambiguidade em cinco dos sete níveis. `N4` cobre `IC4` e `M1`, e `N5`
cobre `IC5` e `M2`: são níveis que a empresa adquirida não distinguia e a NOVAORA
distingue. Não existe mapeamento correto, existe decisão de negócio.

Por isso `N4` e `N5` ficaram deliberadamente fora do mapa aprovado, caem em
`UNMAPPED` e vão para a fila de exceções (ADR-0004, princípio 5).

O limiar de 10% foi um palpite meu ao escrever o catálogo de checks. O realizado
é 13,12%. **Não mexi no limiar**, porque ajustar o limiar para o check passar é
exatamente a classe de intervenção que o ADR-0017 proíbe, e porque a severidade
é CRITICAL e não BLOCKER: o registro entra no analítico e derruba o trust score
do KPI dependente, que é o comportamento desejado.

A decisão é da Sam, e está na lista de pendências.

---

## O que muda daqui para frente

| Achado | Guarda permanente criada |
|---|---|
| 1, execuções desalinhadas | `check_provenance` compara os manifestos antes de comparar dados |
| 2, referência errada | o universo de identidades vira dataset consultável pelos checks |
| 3, data ambígua | marca `__ambiguous` por valor e check WARNING dedicado |
| 4, underflow | cast explícito, e a lição de desconfiar de tipo em aritmética de contagem |
| 5, limiar estourado | nenhuma: o check continua reprovando até haver decisão |

Vale uma observação sobre o conjunto das três fases. Os achados da F1 eram sobre
**o mundo simulado**, os da F2 sobre **o mecanismo que fabrica os defeitos**, e
os da F3 sobre **o instrumento que mede**. A cada camada nova, a validação
precisou passar a olhar para si mesma, e nas três vezes encontrou algo.
