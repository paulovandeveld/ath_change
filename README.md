# ATHChange

ATHChange é um bot de criptomoedas que realiza as seguintes funcionalidades:

- **Obtenção de dados do CoinGecko**: O bot busca informações de mercado via API da CoinGecko e busca a variação de preço em relação ao ATH (All Time High).
- **Integração com MEXC**: O bot interage com a corretora MEXC para verificar a disponibilidade de pares e realizar ordens de compra.
- **Envio de alertas via Telegram**: O bot envia uma lista de criptomoedas que atendem aos critérios definidos através do Telegram.
- **Atualização de Google Sheets**: O bot atualiza uma planilha do Google Sheets com os dados mais recentes de mercado.

## Funcionalidades

1. **Obter dados do CoinGecko**:
   O bot coleta dados de até 5 páginas da API da CoinGecko, para que não ultrapassemos o limite de chamadas do plano gratuito, incluindo informações como nome, símbolo, volume, rank de market cap e variação do preço em relação ao ATH.

2. **Filtrar e ordenar dados**:
   Os dados são filtrados para mostrar apenas as criptomoedas com ranking de market cap abaixo de 500 e ordenados pela variação do preço em relação ao ATH.

3. **Enviar alertas via Telegram**:
   O bot envia mensagens com os 10 principais pares de criptomoedas e as 5 melhores opções para abrir ordens de compra na MEXC.

4. **Executar ordens na MEXC**:
   O bot verifica se os pares estão disponíveis no mercado SPOT da MEXC e realiza ordens de compra quando possível.

## Análise de dados
   O bot foca em moedas que estão próximas ao ATH, pois em um trabalho de análise de dados e backteste, foi constatado um resultado positivo em operações de compra com base nos filtros realizados pelo bot. Apesar de haver uma chance de 'compra de topo', as operações são raṕidas e são encerradas em poucos dias.
   De qualquer moda, este código apresenta apenas um caso de estudo e aplicação envolvendo conexão com várias APIs para realização das análises técnicas em relação ao preço dos ativos e não é uma sugestão de investimento.

## Requisitos

- Python 3.7 ou superior
- Bibliotecas necessárias:
  - `requests`
  - `pandas`
  - `telegram`
  - `google-auth`
  - `google-api-python-client`

Se você quiser contribuir, faça um fork deste repositório, crie uma branch, faça suas alterações e envie um pull request. Para sugestões, abra uma issue!
