# ADR-0004: Resolução de identidade via `xref_employee_identity`

- **Status:** Aceita
- **Data:** 2026-09-11
- **Decisão relacionada:** D4 (Technical Design v0.3)
- **Fase:** F0, vigora a partir da F4

## Contexto

O modelo distingue três conceitos:

| Campo | Significado | Quem gera |
|---|---|---|
| `source_employee_id` | matrícula no sistema de origem | o sistema-fonte |
| `employee_id` | identidade corporativa NOVAORA | o MDM, na camada conformed |
| `employee_key` | chave substituta da versão SCD2 | o pipeline analítico |

O `employee_id` **não existe no RAW** dos sistemas de aquisição nem do ATS
legado (defeito D05), e colide entre sistemas em cerca de 180 casos (defeito
D06). Ele precisa ser resolvido, com método e confiança registrados, e os casos
não resolvidos precisam existir em algum lugar.

## Decisão

Criar a tabela `xref_employee_identity` na camada conformed:

```
xref_id
source_system
source_employee_id
employee_id            # nulo enquanto não resolvido
match_method           # exact_id | document | email | fuzzy_name_dob | manual
match_confidence
match_status           # RESOLVED | AMBIGUOUS | UNRESOLVED | MANUAL_REVIEW
resolved_at
resolved_by
```

Regras:

1. Resolução automática **nunca** promove um match ambíguo. Confiança alta
   melhora a sugestão, não autoriza a decisão, pelo mesmo princípio do
   DE/PARA (ADR-0009 e princípio 5).
2. Registro com `match_status` diferente de `RESOLVED` não entra no analítico
   com `employee_id`, e a contagem desses registros é insumo do trust score.
3. O método de match é registrado, o que torna a resposta "quantas pessoas a
   empresa tem" auditável até o critério usado.

## Alternativas consideradas

1. **Resolver identidade dentro de cada transformação, sem tabela.** Funciona e
   é inauditável: não há onde registrar método, confiança ou ambiguidade.
2. **Guardar a resolução como colunas em `dim_employee`.** Descartada por
   cardinalidade: uma pessoa tem N identidades em N sistemas, e os casos não
   resolvidos não têm `employee_id` no qual se pendurar.
3. **Assumir que `employee_id` sempre existe.** Contradiz o defeito D05, que é
   consequência direta dos incidentes de aquisição.

## Consequências

**Positivas**

- Torna Master Data Management visível, e MDM está nos objetivos da seção 1 da
  Especificação.
- Dá lugar à reconciliação `ATS Employee ID != HRIS Employee ID` da seção 26.
- É um dos artefatos mais reconhecíveis para quem tem experiência real com
  integração de sistemas de RH.

**Negativas**

- Acrescenta um passo obrigatório antes de qualquer junção entre sistemas.
- A fila de `MANUAL_REVIEW` compete por atenção com a fila de exceções de
  DE/PARA; as duas precisam aparecer na mesma tela operacional.

**Riscos e mitigação**

- *Risco:* resolução por nome e data de nascimento gerar falso positivo.
  *Mitigação:* esse método nunca resolve sozinho, ele apenas sugere; o status
  resultante é `MANUAL_REVIEW`.

## Referências

- Technical Design v0.3, seção 6.1
- Especificação do Universo v1.0, seções 1, 6 e 26
- `config/defects.yaml`: D05, D06, D22
