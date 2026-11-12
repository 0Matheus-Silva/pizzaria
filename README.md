# Bella Pizza

Cardápio estático feito com HTML, CSS e JavaScript. Não precisa instalar dependências nem configurar um servidor Python para publicar.

## Abrir e publicar

- Para visualizar, abra `index.html` no navegador. A busca, os filtros e a sacola funcionam sem uma etapa de build.
- Para publicar no GitHub Pages, selecione a branch do projeto e a pasta raiz (`/`) em **Settings → Pages**.

## Catálogo e sacola

O catálogo em `products.js` preserva os 18 produtos e preços do catálogo demonstrativo anterior: 12 pizzas e 6 bebidas. As imagens dos produtos estão em `images/products/` e também são servidas localmente.

A sacola e os pedidos de demonstração ficam salvos no navegador e só podem ser vistos no mesmo dispositivo e perfil do navegador. O checkout exige nome, sobrenome, endereço e a seleção de uma forma de pagamento na entrega: dinheiro, cartão de débito ou cartão de crédito. Após a solicitação, a página mostra o pedido como recebido pela loja e aguardando aceitação, com uma previsão simulada de 30 a 40 minutos.

> **Simulação de teste:** o site é estático e não envia pedidos à loja, não confirma disponibilidade, não processa pagamentos e não realiza entregas. O status, a previsão e os dados ficam apenas neste navegador; não há conta de cliente, painel administrativo ou banco de dados conectado. Não use dados pessoais reais nesta demonstração.

## Imagens

As fotografias foram obtidas do [Unsplash](https://unsplash.com/license) e incluídas como arquivos locais para que o catálogo não dependa de um serviço externo de imagens. A foto de **Banana com Canela** é de Amanda Coutinho, via [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Sweet_pizza_(50870993271).jpg), licenciada em [CC BY 2.0](https://creativecommons.org/licenses/by/2.0/).
