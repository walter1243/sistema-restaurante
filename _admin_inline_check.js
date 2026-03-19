// CONTEXTO
        const queryParams = new URLSearchParams(window.location.search);
        const slugAtual = queryParams.get('slug') || 'demo';
        const tokenUrl = queryParams.get('token') || '';

        let contexto = {
            slug: slugAtual,
            token: tokenUrl || localStorage.getItem(`token_admin_${slugAtual}`) || localStorage.getItem('token_admin') || '',
            restaurante: {},
            produtos: [],
            pedidos: [],
            mesas: [],
            categorias: ['Entrada', 'Prato Principal', 'Acompanhamento', 'Bebida', 'Sobremesa'],
            horariosCategoria: {},
            dragCategoriaIndice: null,
            editandoProduto: null,
            filtroProduto: 'todos',
            filtroPedidos: 'abertos',
            caixaAberto: false,
            caixaAbertura: null,
            caixaValorInicial: 0,
            caixaMovimentos: [],
            entregadores: [],
            corridaPedidoId: null,
            corridaEntregadorId: null,
            corridaAutoSeguir: false,
            mapaCorrida: null,
            camadaCorrida: null,
            geoCache: {},
            modoApi: true,
            automacaoDeliveryAtiva: true,
            automacaoExecutando: false,
            automacaoFalhasPorPedido: {}
        };

        let mesaContaAtual = null;
        let intervalPedidos = null;
        let intervalEntregadores = null;
        let ultimoTotalPendentesNav = null;
        let navBadgePulseTimer = null;
        let ultimoTotalPendentesDeliveryNav = null;
        let navDeliveryBadgePulseTimer = null;

        const API_URL = (() => {
            const q = new URLSearchParams(window.location.search);
            const apiParam = (q.get('api') || '').trim();
            if (apiParam) {
                const normalizado = apiParam.replace(/\/$/, '');
                localStorage.setItem('api_base_url', normalizado);
                return normalizado;
            }
            const salvo = (localStorage.getItem('api_base_url') || '').trim();
            if (salvo) return salvo.replace(/\/$/, '');
            const host = window.location.hostname || '127.0.0.1';
            const local = host === 'localhost' || host === '127.0.0.1';
            if (local) return `${window.location.protocol}//${host}:8001`;
            return '';
        })();

        function storageKey(chave) {
            return `${chave}_${contexto.slug}`;
        }

        function salvarTokenLocal() {
            if (contexto.token) {
                localStorage.setItem(`token_admin_${contexto.slug}`, contexto.token);
                localStorage.setItem('token_admin', contexto.token);
            }
        }

        function normalizarCategorias(lista = []) {
            const base = ['Entrada', 'Prato Principal', 'Acompanhamento', 'Bebida', 'Sobremesa'];
            const categoriasEntrada = lista.filter(Boolean).map(c => c.trim()).filter(Boolean);
            const extrasBase = base.filter(c => !categoriasEntrada.includes(c));
            return [...new Set([...categoriasEntrada, ...extrasBase])];
        }

        function renderizarSelectCategorias(valorSelecionado = '') {
            const select = document.getElementById('produto-categoria');
            select.innerHTML = contexto.categorias.map(categoria => `
                <option value="${categoria}" ${categoria === valorSelecionado ? 'selected' : ''}>${categoria}</option>
            `).join('');

            document.getElementById('categorias-salvas').innerHTML = contexto.categorias.map(categoria => `
                <span class="tag-item">${categoria}</span>
            `).join('');

            renderizarOrdenacaoCategorias();
            renderizarHorariosCategorias();
        }

        function renderizarHorariosCategorias() {
            const lista = document.getElementById('categoria-horarios-lista');
            if (!lista) return;

            lista.innerHTML = contexto.categorias.map(categoria => {
                const horario = contexto.horariosCategoria[categoria] || {};
                return `
                    <div class="schedule-item">
                        <span>${categoria}</span>
                        <input type="time" class="form-input" data-categoria-inicio="${categoria}" value="${horario.inicio || ''}">
                        <input type="time" class="form-input" data-categoria-fim="${categoria}" value="${horario.fim || ''}">
                    </div>
                `;
            }).join('');
        }

        function coletarHorariosCategoriaFormulario() {
            const horarios = {};
            contexto.categorias.forEach(categoria => {
                const inicio = document.querySelector(`[data-categoria-inicio="${categoria}"]`)?.value || '';
                const fim = document.querySelector(`[data-categoria-fim="${categoria}"]`)?.value || '';
                if (inicio || fim) {
                    horarios[categoria] = { inicio, fim };
                }
            });
            contexto.horariosCategoria = horarios;
            return horarios;
        }

        function renderizarOrdenacaoCategorias() {
            const lista = document.getElementById('categorias-ordem-lista');
            if (!lista) return;

            lista.innerHTML = contexto.categorias.map((categoria, idx) => `
                <div class="category-order-item" draggable="true" data-index="${idx}" ondragstart="iniciarDragCategoria(event, ${idx})" ondragend="finalizarDragCategoria(event)" ondragover="permitirDropCategoria(event)" ondragleave="event.currentTarget.classList.remove('drag-over')" ondrop="soltarCategoria(event, ${idx})">
                    <span class="category-order-name"><i class="fas fa-grip-vertical drag-handle"></i>${categoria}</span>
                </div>
            `).join('');
        }

        function iniciarDragCategoria(event, indice) {
            contexto.dragCategoriaIndice = indice;
            event.dataTransfer.effectAllowed = 'move';
            event.dataTransfer.setData('text/plain', String(indice));
            event.currentTarget.classList.add('dragging');
        }

        function permitirDropCategoria(event) {
            event.preventDefault();
            event.dataTransfer.dropEffect = 'move';
            event.currentTarget.classList.add('drag-over');
        }

        function soltarCategoria(event, indiceDestino) {
            event.preventDefault();
            event.currentTarget.classList.remove('drag-over');

            const indiceOrigem = Number.isInteger(contexto.dragCategoriaIndice)
                ? contexto.dragCategoriaIndice
                : parseInt(event.dataTransfer.getData('text/plain'), 10);

            if (Number.isNaN(indiceOrigem) || indiceOrigem === indiceDestino) {
                return;
            }

            const categorias = [...contexto.categorias];
            const [movida] = categorias.splice(indiceOrigem, 1);
            categorias.splice(indiceDestino, 0, movida);
            contexto.categorias = categorias;

            const local = JSON.parse(localStorage.getItem(storageKey('restaurante_config')) || '{}');
            local.categorias = contexto.categorias;
            localStorage.setItem(storageKey('restaurante_config'), JSON.stringify(local));
            renderizarSelectCategorias(document.getElementById('produto-categoria')?.value || '');
            contexto.dragCategoriaIndice = null;
        }

        function finalizarDragCategoria(event) {
            event.currentTarget.classList.remove('dragging');
            document.querySelectorAll('.category-order-item.drag-over').forEach(item => item.classList.remove('drag-over'));
            contexto.dragCategoriaIndice = null;
        }

        function atualizarPreviewCapa(imagem = '') {
            const preview = document.getElementById('capa-preview');
            const thumb = document.getElementById('capa-thumb-preview');
            if (imagem) {
                preview.innerHTML = `<img src="${imagem}">`;
                preview.dataset.base64 = imagem;
                if (thumb) thumb.innerHTML = `<img src="${imagem}">`;
            } else {
                preview.innerHTML = 'Capa do Cardápio';
                preview.removeAttribute('data-base64');
                if (thumb) thumb.innerHTML = 'Topo do cardápio';
            }

            const capaCss = imagem ? `url("${imagem}")` : 'none';
            document.documentElement.style.setProperty('--admin-live-cover', capaCss);
            atualizarBloqueioCoresTema();
        }

        function atualizarPosicaoCapaPreview() {
            const posicao = document.getElementById('config-capa-posicao').value || 'center';
            document.documentElement.style.setProperty('--admin-live-cover-position', posicao);
        }

        function atualizarPreviewTema() {
            const corPrimaria = document.getElementById('config-cor-primaria').value || '#3b82f6';
            const corSecundaria = document.getElementById('config-cor-secundaria').value || '#10b981';
            const corDestaque = document.getElementById('config-cor-destaque').value || '#1e293b';
            const estiloBotao = document.getElementById('config-estilo-botao').value || 'rounded';

            document.querySelectorAll('.menu-live-chip').forEach((chip, idx) => {
                chip.style.background = idx % 2 === 0 ? corPrimaria + '22' : corSecundaria + '22';
            });

            const liveLogo = document.getElementById('menu-live-logo');
            if (liveLogo) {
                liveLogo.style.borderRadius = estiloBotao === 'pill' ? '999px' : (estiloBotao === 'soft' ? '1rem' : '0.5rem');
            }

            document.documentElement.style.setProperty('--admin-preview-primary', corPrimaria);
            document.documentElement.style.setProperty('--admin-preview-secondary', corSecundaria);
            document.documentElement.style.setProperty('--admin-preview-accent', corDestaque);
            document.documentElement.style.setProperty('--admin-preview-primary-soft', hexParaRgba(corPrimaria, 0.14));
            document.documentElement.style.setProperty('--admin-preview-secondary-soft', hexParaRgba(corSecundaria, 0.16));
            document.documentElement.style.setProperty('--admin-preview-accent-soft', hexParaRgba(corDestaque, 0.12));
        }

        function atualizarBloqueioCoresTema() {
            const possuiCapa = !!(document.getElementById('capa-preview')?.dataset.base64 || '').trim();
            const possuiLogo = !!(document.getElementById('logo-preview')?.dataset.base64 || '').trim();
            const bloquear = possuiCapa && possuiLogo;

            ['config-cor-primaria', 'config-cor-secundaria', 'config-cor-destaque'].forEach((idCampo) => {
                const campo = document.getElementById(idCampo);
                if (!campo) return;
                campo.disabled = bloquear;
                campo.style.opacity = bloquear ? '0.55' : '1';
                campo.style.cursor = bloquear ? 'not-allowed' : 'pointer';
            });

            const aviso = document.getElementById('tema-bloqueio-aviso');
            if (aviso) {
                aviso.textContent = bloquear
                    ? 'Com capa + logo definidos, as cores ficam bloqueadas automaticamente.'
                    : 'As cores são opcionais para quem não usa capa + logo.';
            }
        }

        function hexParaRgba(hex, alpha = 1) {
            const cor = (hex || '').replace('#', '').trim();
            if (![3, 6].includes(cor.length)) return `rgba(59, 130, 246, ${alpha})`;

            const normalizada = cor.length === 3 ? cor.split('').map(char => char + char).join('') : cor;
            const numero = parseInt(normalizada, 16);
            const r = (numero >> 16) & 255;
            const g = (numero >> 8) & 255;
            const b = numero & 255;
            return `rgba(${r}, ${g}, ${b}, ${alpha})`;
        }

        function formatarDataHora(dataIso) {
            if (!dataIso) return '—';
            const data = new Date(dataIso);
            if (Number.isNaN(data.getTime())) return '—';
            return data.toLocaleString('pt-BR', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        }

        function atualizarPainelPublicacao() {
            const local = JSON.parse(localStorage.getItem(storageKey('restaurante_config')) || '{}');
            const publicadoEm = local.publicado_em || '';
            const rascunhoEm = local.rascunho_em || '';

            document.getElementById('status-publicacao-texto').textContent = publicadoEm
                ? `Publicado em ${formatarDataHora(publicadoEm)}`
                : 'Sem publicação ainda';
            document.getElementById('status-publicacao-detalhe').textContent = publicadoEm
                ? 'Essa é a última versão enviada para o cliente.'
                : 'Publique para atualizar a página do cliente.';

            document.getElementById('status-rascunho-texto').textContent = rascunhoEm
                ? `Rascunho salvo em ${formatarDataHora(rascunhoEm)}`
                : 'Nenhum rascunho salvo';
            document.getElementById('status-rascunho-detalhe').textContent = rascunhoEm
                ? 'Use Publicar Alterações para enviar a versão local.'
                : 'As alterações locais ficam guardadas no admin.';
        }

        function obterOrigemBase() {
            const urlFixa = (contexto.restaurante.url_base_publica || '').trim().replace(/\/$/, '');
            return urlFixa || window.location.origin || 'http://localhost:5500';
        }

        function obterLinkCardapioPublico() {
            return `${obterOrigemBase()}/index.html?slug=${encodeURIComponent(contexto.slug)}&mesa=1`;
        }

        function obterLinkCardapioPreview() {
            return `${obterOrigemBase()}/index.html?slug=${encodeURIComponent(contexto.slug)}&mesa=1&preview=1&t=${Date.now()}`;
        }

        function obterLinkCardapioPorMesa(mesa = 1) {
            return `${obterOrigemBase()}/index.html?slug=${encodeURIComponent(contexto.slug)}&mesa=${encodeURIComponent(mesa)}`;
        }

        function renderizarSeletorMesaPublica() {
            const select = document.getElementById('preview-mesa-publica');
            if (!select) return;
            const totalMesas = Math.max(1, Number(contexto.restaurante.total_mesas || 1));
            const valorAtual = Number(select.value || 1);
            select.innerHTML = Array.from({ length: totalMesas }, (_, indice) => {
                const mesa = indice + 1;
                return `<option value="${mesa}" ${mesa === valorAtual ? 'selected' : ''}>Mesa ${mesa}</option>`;
            }).join('');
            if (valorAtual > totalMesas) {
                select.value = '1';
            }
            atualizarPreviewLinkPublico();
        }

        function atualizarPreviewLinkPublico() {
            const select = document.getElementById('preview-mesa-publica');
            const destino = document.getElementById('preview-link-publico');
            if (!select || !destino) return;
            destino.textContent = obterLinkCardapioPorMesa(select.value || 1);
            gerarQrCodeMesa();
        }

        function gerarQrCodeMesa() {
            const select = document.getElementById('preview-mesa-publica');
            const container = document.getElementById('qr-code-mesa');
            const label = document.getElementById('qr-label-mesa');
            if (!container || !select) return;
            const mesa = select.value || 1;
            const link = obterLinkCardapioPorMesa(mesa);
            if (label) label.textContent = `QR Code — Mesa ${mesa}`;
            container.innerHTML = '';
            if (typeof QRCode !== 'undefined') {
                new QRCode(container, {
                    text: link,
                    width: 180,
                    height: 180,
                    colorDark: '#000000',
                    colorLight: '#ffffff',
                    correctLevel: QRCode.CorrectLevel.H
                });
            } else {
                container.innerHTML = '<span style="color:#ef4444;font-size:0.8rem;">QRCode.js indisponível</span>';
            }
        }

        function baixarQrCodeMesa() {
            const container = document.getElementById('qr-code-mesa');
            const select = document.getElementById('preview-mesa-publica');
            const mesa = select?.value || 1;
            const canvas = container?.querySelector('canvas');
            const img = container?.querySelector('img');
            let src = '';
            if (canvas) { src = canvas.toDataURL('image/png'); }
            else if (img) { src = img.src; }
            else { alert('Gere o QR Code primeiro selecionando uma mesa.'); return; }
            const a = document.createElement('a');
            a.href = src;
            a.download = `qrcode-mesa-${mesa}.png`;
            a.click();
        }

        function imprimirQrCodeMesa() {
            const container = document.getElementById('qr-code-mesa');
            const select = document.getElementById('preview-mesa-publica');
            const mesa = select?.value || 1;
            const canvas = container?.querySelector('canvas');
            const img = container?.querySelector('img');
            let src = '';
            if (canvas) { src = canvas.toDataURL('image/png'); }
            else if (img) { src = img.src; }
            else { alert('Gere o QR Code primeiro selecionando uma mesa.'); return; }
            const janela = window.open('', '_blank', 'width=420,height=540');
            janela.document.write(`
                <html><head><title>QR Code Mesa ${mesa}</title>
                <style>body{margin:0;display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;gap:1.2rem;}p{font-size:1.2rem;font-weight:700;color:#1e293b;}img{width:260px;height:260px;}</style></head>
                <body><p>Mesa ${mesa}</p><img src="${src}" /><script>window.onload=()=>{window.print();window.close();}<\/script></body></html>
            `);
            janela.document.close();
        }

        function abrirPreviewMesaPublica() {
            const mesa = document.getElementById('preview-mesa-publica')?.value || 1;
            salvarSnapshotPreviewLocal();
            window.open(obterLinkCardapioPorMesa(mesa), '_blank');
        }

        async function copiarPreviewMesaPublica() {
            const mesa = document.getElementById('preview-mesa-publica')?.value || 1;
            const link = obterLinkCardapioPorMesa(mesa);
            try {
                await navigator.clipboard.writeText(link);
                alert(`Link da Mesa ${mesa} copiado!`);
            } catch (erro) {
                window.prompt(`Copie o link da Mesa ${mesa}:`, link);
            }
        }

        function abrirCardapioPublico() {
            salvarSnapshotPreviewLocal();
            window.open(obterLinkCardapioPreview(), '_blank');
        }

        async function copiarLinkCardapio() {
            const link = obterLinkCardapioPublico();
            try {
                await navigator.clipboard.writeText(link);
                alert('Link do cardápio copiado!');
            } catch (erro) {
                window.prompt('Copie o link do cardápio:', link);
            }
        }

        function salvarSnapshotPreviewLocal() {
            try {
                const { horariosCategoria } = obterPayloadConfiguracoes();
                const localAtual = JSON.parse(localStorage.getItem(storageKey('restaurante_config')) || '{}');
                localStorage.setItem(storageKey('restaurante_config'), JSON.stringify({
                    ...contexto.restaurante,
                    categorias: contexto.categorias,
                    horarios_categoria: horariosCategoria,
                    publicado_em: localAtual.publicado_em || null,
                    rascunho_em: new Date().toISOString()
                }));
            } catch (erro) {
                console.warn('Falha ao preparar snapshot do preview:', erro?.message || erro);
            }
        }

        function atualizarPreviewLogo(imagem = '') {
            const preview = document.getElementById('logo-preview');
            const thumb = document.getElementById('logo-thumb-preview');
            const liveLogo = document.getElementById('menu-live-logo');
            const livePlaceholder = document.getElementById('menu-live-logo-placeholder');

            if (imagem) {
                preview.innerHTML = `<img src="${imagem}" style="width: 100%; height: 100%; object-fit: contain;">`;
                preview.dataset.base64 = imagem;
                if (thumb) thumb.innerHTML = `<img src="${imagem}">`;
                liveLogo.src = imagem;
                liveLogo.style.display = 'block';
                livePlaceholder.style.display = 'none';
            } else {
                preview.innerHTML = 'Logo do Restaurante';
                preview.removeAttribute('data-base64');
                if (thumb) thumb.innerHTML = 'Logo do restaurante';
                liveLogo.removeAttribute('src');
                liveLogo.style.display = 'none';
                livePlaceholder.style.display = 'inline-flex';
            }

            atualizarBloqueioCoresTema();
        }

        function obterHorarioProduto(produto) {
            const inicio = produto.horario_inicio || contexto.horariosCategoria?.[produto.categoria]?.inicio || '';
            const fim = produto.horario_fim || contexto.horariosCategoria?.[produto.categoria]?.fim || '';
            return { inicio, fim };
        }

        function produtoDisponivelAgora(produto) {
            if (produto.disponivel === false) return false;
            const { inicio, fim } = obterHorarioProduto(produto);
            if (!inicio || !fim) return true;

            const agora = new Date();
            const atual = `${String(agora.getHours()).padStart(2, '0')}:${String(agora.getMinutes()).padStart(2, '0')}`;
            if (inicio <= fim) {
                return atual >= inicio && atual <= fim;
            }
            return atual >= inicio || atual <= fim;
        }

        function obterStatusProduto(produto) {
            const { inicio, fim } = obterHorarioProduto(produto);
            const horarioTexto = inicio && fim ? `${inicio} às ${fim}` : '';

            if (produto.disponivel === false) {
                return {
                    principal: { texto: 'Desativado manualmente', tipo: 'danger', icone: 'fa-ban' },
                    horario: horarioTexto
                };
            }

            if (horarioTexto) {
                return {
                    principal: produtoDisponivelAgora(produto)
                        ? { texto: 'Disponível agora', tipo: 'success', icone: 'fa-clock' }
                        : { texto: 'Fora do horário', tipo: 'warning', icone: 'fa-clock' },
                    horario: horarioTexto
                };
            }

            return {
                principal: { texto: 'Sempre disponível', tipo: 'info', icone: 'fa-circle-check' },
                horario: ''
            };
        }

        function renderizarResumoProdutos() {
            const resumo = {
                total: contexto.produtos.length,
                ativos: 0,
                agendados: 0,
                pausados: 0
            };

            contexto.produtos.forEach(produto => {
                const { inicio, fim } = obterHorarioProduto(produto);
                if (produto.disponivel === false) {
                    resumo.pausados += 1;
                    return;
                }
                if (inicio && fim) resumo.agendados += 1;
                if (produtoDisponivelAgora(produto)) resumo.ativos += 1;
            });

            const container = document.getElementById('resumo-produtos-status');
            if (!container) return;
            container.innerHTML = `
                <div class="product-summary-card"><span>Total de produtos</span><strong>${resumo.total}</strong></div>
                <div class="product-summary-card"><span>Disponíveis agora</span><strong>${resumo.ativos}</strong></div>
                <div class="product-summary-card"><span>Com horário</span><strong>${resumo.agendados}</strong></div>
                <div class="product-summary-card"><span>Pausados</span><strong>${resumo.pausados}</strong></div>
            `;
        }

        function definirFiltroProduto(filtro, event) {
            contexto.filtroProduto = filtro;
            document.querySelectorAll('.filter-chip').forEach(btn => btn.classList.remove('active'));
            event.currentTarget.classList.add('active');
            filtrarProdutos();
        }

        async function previewCapa(event) {
            const file = event.target.files[0];
            if (!file) return;
            try {
                const imagemRecortada = await gerarImagemRecortada(file, 1600, 720);
                atualizarPreviewCapa(imagemRecortada);
            } catch (erro) {
                const reader = new FileReader();
                reader.onload = (e) => atualizarPreviewCapa(e.target.result);
                reader.readAsDataURL(file);
            }
        }

        function gerarImagemRecortada(file, larguraDestino, alturaDestino) {
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = (eventoLeitura) => {
                    const img = new Image();
                    img.onload = () => {
                        const proporcaoDestino = larguraDestino / alturaDestino;
                        const proporcaoOrigem = img.width / img.height;

                        let recorteX = 0;
                        let recorteY = 0;
                        let recorteLargura = img.width;
                        let recorteAltura = img.height;

                        if (proporcaoOrigem > proporcaoDestino) {
                            recorteLargura = img.height * proporcaoDestino;
                            recorteX = (img.width - recorteLargura) / 2;
                        } else {
                            recorteAltura = img.width / proporcaoDestino;
                            recorteY = (img.height - recorteAltura) / 2;
                        }

                        const canvas = document.createElement('canvas');
                        canvas.width = larguraDestino;
                        canvas.height = alturaDestino;
                        const contextoCanvas = canvas.getContext('2d');

                        contextoCanvas.drawImage(
                            img,
                            recorteX,
                            recorteY,
                            recorteLargura,
                            recorteAltura,
                            0,
                            0,
                            larguraDestino,
                            alturaDestino
                        );

                        resolve(canvas.toDataURL('image/jpeg', 0.92));
                    };
                    img.onerror = () => reject(new Error('Imagem inválida'));
                    img.src = eventoLeitura.target.result;
                };
                reader.onerror = () => reject(new Error('Erro ao ler arquivo'));
                reader.readAsDataURL(file);
            });
        }

        async function previewLogo(event) {
            const file = event.target.files[0];
            if (!file) return;
            try {
                const imagemRecortada = await gerarImagemRecortada(file, 900, 270);
                atualizarPreviewLogo(imagemRecortada);
            } catch (erro) {
                const reader = new FileReader();
                reader.onload = (e) => atualizarPreviewLogo(e.target.result);
                reader.readAsDataURL(file);
            }
        }

        function aplicarConfiguracaoNaTela() {
            document.getElementById('restaurante-nome').textContent = contexto.restaurante.nome_unidade || 'Demo';
            document.getElementById('config-nome').value = contexto.restaurante.nome_unidade || '';
            document.getElementById('config-cnpj').value = contexto.restaurante.cnpj || '';
            document.getElementById('config-slug').value = contexto.slug;
            document.getElementById('config-token').value = contexto.token || 'Sem token configurado';
            document.getElementById('config-mesas').value = contexto.restaurante.total_mesas || 10;
            document.getElementById('config-url-base').value = contexto.restaurante.url_base_publica || '';
            document.getElementById('config-capa-posicao').value = contexto.restaurante.capa_posicao || 'center';
            document.getElementById('config-cor-primaria').value = contexto.restaurante.tema_cor_primaria || '#3b82f6';
            document.getElementById('config-cor-secundaria').value = contexto.restaurante.tema_cor_secundaria || '#10b981';
            document.getElementById('config-cor-destaque').value = contexto.restaurante.tema_cor_destaque || '#1e293b';
            document.getElementById('config-estilo-botao').value = contexto.restaurante.estilo_botao || 'rounded';
            document.getElementById('config-delivery-ativo').checked = !!contexto.restaurante.delivery_ativo;
            document.getElementById('config-delivery-origem').value = contexto.restaurante.delivery_endereco_origem || '';
            document.getElementById('config-maps-key').value = contexto.restaurante.delivery_google_maps_api_key || '';
            document.getElementById('config-whatsapp-entregador').value = contexto.restaurante.delivery_whatsapp_entregador || '';
            document.getElementById('config-whatsapp-api-ativo').checked = !!contexto.restaurante.whatsapp_api_ativo;
            document.getElementById('config-whatsapp-phone-id').value = contexto.restaurante.whatsapp_phone_number_id || '';
            document.getElementById('config-whatsapp-access-token').value = contexto.restaurante.whatsapp_access_token || '';
            document.getElementById('config-whatsapp-verify-token').value = contexto.restaurante.whatsapp_verify_token || '';
            atualizarPreviewCapa(contexto.restaurante.capa_cardapio || '');
            atualizarPosicaoCapaPreview();
            atualizarPreviewLogo(contexto.restaurante.logo || '');
            atualizarPreviewTema();
            atualizarBloqueioCoresTema();
            renderizarSelectCategorias();
            renderizarSeletorMesaPublica();
            atualizarPainelPublicacao();
            atualizarBadgePlanoSuperAdmin();
        }

        function atualizarBadgePlanoSuperAdmin() {
            const badge = document.getElementById('status-badge');
            if (!badge) return;
            badge.removeAttribute('style');
            badge.textContent = 'Plano SaaS';
            badge.className = 'header-badge badge-sem-data';
            badge.title = 'Fatura e validade são gerenciadas no Super Admin';
        }

        // INICIALIZAÇÃO
        function mostrarFalhaInicializacao(mensagem, erro = null) {
            console.error('Falha na inicialização do painel admin:', erro || mensagem);
            const container = document.getElementById('pedidos-container');
            if (container) {
                container.innerHTML = `
                    <div class="card" style="padding:1rem;border:1px solid #fecaca;background:#fff1f2;color:#9f1239;">
                        <strong>Não foi possível carregar o painel completamente.</strong><br>
                        <span style="font-size:0.86rem;">${mensagem}</span><br>
                        <span style="font-size:0.8rem;color:#7f1d1d;">Recarregue com Ctrl+F5 ou abra em aba anônima.</span>
                    </div>
                `;
            }
        }

        async function inicializar() {
            try {
                document.addEventListener('keydown', (event) => {
                    if (event.key === 'Escape') fecharMenu();
                });

                window.addEventListener('resize', () => {
                    if (window.innerWidth > 768) fecharMenu();
                });

                salvarTokenLocal();
                await carregarConfiguracao();
                await carregarProdutos();
                await carregarPedidos();
                await carregarMesas();
                await carregarEntregadores();
                renderizarTudo();
                iniciarAtualizacaoTempoReal();
            } catch (erro) {
                try {
                    contexto.modoApi = false;
                    contexto.pedidos = JSON.parse(localStorage.getItem(storageKey('pedidos')) || '[]');
                    contexto.produtos = JSON.parse(localStorage.getItem(storageKey('produtos')) || '[]');
                    contexto.entregadores = JSON.parse(localStorage.getItem(storageKey('entregadores')) || '[]');
                    await carregarMesas();
                    renderizarTudo();
                } catch (_) {}
                mostrarFalhaInicializacao('Erro de carregamento de script/API. O painel entrou em modo de segurança.', erro);
            }
        }

        function iniciarAtualizacaoTempoReal() {
            if (intervalPedidos) {
                clearInterval(intervalPedidos);
            }
            intervalPedidos = setInterval(async () => {
                await carregarPedidos();
                renderizarPedidos();
                renderizarMesas();
                atualizarKPIsPedidos();
                atualizarPainelCorridaTempoReal();
            }, 12000);

            if (intervalEntregadores) {
                clearInterval(intervalEntregadores);
            }
            intervalEntregadores = setInterval(async () => {
                await carregarEntregadores();
                renderizarEntregadores();
                atualizarPainelCorridaTempoReal();
            }, 15000);
        }

        function mudarSecao(secao) {
            document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById(secao).classList.add('active');
            document.querySelector(`.nav-item[onclick="mudarSecao('${secao}')"]`).classList.add('active');
            const btnVoltar = document.getElementById('btn-voltar-dashboard');
            if (btnVoltar) {
                btnVoltar.classList.toggle('visible', secao !== 'dashboard');
            }
            fecharMenu();
        }

        function voltarDashboard() {
            mudarSecao('dashboard');
        }

        function toggleMenu() {
            const sidebar = document.querySelector('.sidebar');
            const overlay = document.getElementById('sidebar-overlay');
            if (!sidebar || !overlay) return;
            const abrir = !sidebar.classList.contains('open');
            sidebar.classList.toggle('open', abrir);
            overlay.classList.toggle('active', abrir);
            document.body.classList.toggle('menu-open', abrir);
        }

        function fecharMenu() {
            const sidebar = document.querySelector('.sidebar');
            const overlay = document.getElementById('sidebar-overlay');
            if (!sidebar || !overlay) return;
            sidebar.classList.remove('open');
            overlay.classList.remove('active');
            document.body.classList.remove('menu-open');
        }

        function togglePreviewConfiguracoes() {
            const painel = document.getElementById('preview-config-extra');
            const botao = document.getElementById('btn-preview-config');
            if (!painel || !botao) return;
            const abrir = !painel.classList.contains('active');
            painel.classList.toggle('active', abrir);
            botao.innerHTML = abrir
                ? '<i class="fas fa-eye-slash"></i> Ocultar detalhes'
                : '<i class="fas fa-eye"></i> Ver detalhes';
        }

        // CONFIGURAÇÃO
        async function carregarConfiguracao() {
            contexto.modoApi = !!contexto.token;
            try {
                const res = await fetch(`${API_URL}/api/admin/restaurante/${contexto.slug}`, {
                    headers: { 'token-acesso': contexto.token }
                });
                if (res.ok) {
                    const data = await res.json();
                    contexto.restaurante = {
                        nome_unidade: data.nome_unidade || 'Restaurante Demo',
                        cnpj: data.cnpj || '',
                        total_mesas: data.total_mesas || 10,
                        url_base_publica: data.url_base_publica || '',
                        capa_cardapio: data.capa_cardapio || '',
                        capa_posicao: data.capa_posicao || 'center',
                        logo: data.logo || '',
                        tema_cor_primaria: data.tema_cor_primaria || '#3b82f6',
                        tema_cor_secundaria: data.tema_cor_secundaria || '#10b981',
                        tema_cor_destaque: data.tema_cor_destaque || '#1e293b',
                        estilo_botao: data.estilo_botao || 'rounded',
                        delivery_ativo: !!data.delivery_ativo,
                        delivery_endereco_origem: data.delivery_endereco_origem || '',
                        delivery_google_maps_api_key: data.delivery_google_maps_api_key || '',
                        delivery_whatsapp_entregador: data.delivery_whatsapp_entregador || '',
                        whatsapp_api_ativo: !!data.whatsapp_api_ativo,
                        whatsapp_phone_number_id: data.whatsapp_phone_number_id || '',
                        whatsapp_access_token: data.whatsapp_access_token || '',
                        whatsapp_verify_token: data.whatsapp_verify_token || ''
                    };
                    contexto.categorias = normalizarCategorias(data.categorias || []);
                    contexto.horariosCategoria = data.horarios_categoria || {};
                    localStorage.setItem(storageKey('restaurante_config'), JSON.stringify({
                        ...contexto.restaurante,
                        categorias: contexto.categorias,
                        horarios_categoria: contexto.horariosCategoria,
                        publicado_em: data.publicado_em || null,
                        rascunho_em: data.rascunho_em || null
                    }));
                    salvarTokenLocal();
                    aplicarConfiguracaoNaTela();
                    return;
                }
                contexto.modoApi = false;
            } catch (e) {
                console.log('Usando configuração local');
            }

            contexto.modoApi = false;
            const local = JSON.parse(localStorage.getItem(storageKey('restaurante_config')) || '{}');
            contexto.restaurante = {
                nome_unidade: local.nome_unidade || 'Restaurante Demo',
                cnpj: local.cnpj || '',
                total_mesas: local.total_mesas || 10,
                url_base_publica: local.url_base_publica || '',
                capa_cardapio: local.capa_cardapio || '',
                capa_posicao: local.capa_posicao || 'center',
                logo: local.logo || '',
                tema_cor_primaria: local.tema_cor_primaria || '#3b82f6',
                tema_cor_secundaria: local.tema_cor_secundaria || '#10b981',
                tema_cor_destaque: local.tema_cor_destaque || '#1e293b',
                estilo_botao: local.estilo_botao || 'rounded',
                delivery_ativo: !!local.delivery_ativo,
                delivery_endereco_origem: local.delivery_endereco_origem || '',
                delivery_google_maps_api_key: local.delivery_google_maps_api_key || '',
                delivery_whatsapp_entregador: local.delivery_whatsapp_entregador || '',
                whatsapp_api_ativo: !!local.whatsapp_api_ativo,
                whatsapp_phone_number_id: local.whatsapp_phone_number_id || '',
                whatsapp_access_token: local.whatsapp_access_token || '',
                whatsapp_verify_token: local.whatsapp_verify_token || ''
            };
            contexto.categorias = normalizarCategorias(local.categorias || []);
            contexto.horariosCategoria = local.horarios_categoria || {};
            aplicarConfiguracaoNaTela();
        }

        // PRODUTOS
        async function carregarProdutos() {
            try {
                const res = await fetch(`${API_URL}/api/admin/cardapio/${contexto.slug}`, {
                    headers: { 'token-acesso': contexto.token }
                });
                if (res.ok) {
                    contexto.produtos = await res.json();
                    localStorage.setItem(storageKey('produtos'), JSON.stringify(contexto.produtos));
                    contexto.modoApi = true;
                } else {
                    contexto.produtos = JSON.parse(localStorage.getItem(storageKey('produtos')) || '[]');
                    contexto.modoApi = false;
                }
            } catch (e) {
                contexto.produtos = JSON.parse(localStorage.getItem(storageKey('produtos')) || '[]');
                contexto.modoApi = false;
            }
        }

        function abrirModalProduto(id = null) {
            contexto.editandoProduto = id;
            renderizarSelectCategorias();
            if (id !== null) {
                const produto = contexto.produtos.find(p => p.id === id);
                if (produto) {
                    document.getElementById('produto-nome').value = produto.nome || '';
                    renderizarSelectCategorias(produto.categoria || '');
                    document.getElementById('produto-preco').value = produto.preco || '';
                    document.getElementById('produto-descricao').value = produto.descricao || '';
                    document.getElementById('produto-disponivel').checked = produto.disponivel !== false;
                    document.getElementById('produto-horario-inicio').value = produto.horario_inicio || '';
                    document.getElementById('produto-horario-fim').value = produto.horario_fim || '';
                    
                    if (produto.imagem) {
                        const preview = document.getElementById('imagem-preview');
                        preview.innerHTML = `<img src="${produto.imagem}">`;
                        preview.dataset.base64 = produto.imagem;
                    }
                }
            } else {
                document.getElementById('produto-nome').value = '';
                renderizarSelectCategorias('Prato Principal');
                document.getElementById('produto-preco').value = '';
                document.getElementById('produto-descricao').value = '';
                document.getElementById('produto-disponivel').checked = true;
                document.getElementById('produto-horario-inicio').value = '';
                document.getElementById('produto-horario-fim').value = '';
                document.getElementById('nova-categoria').value = '';
                document.getElementById('imagem-preview').innerHTML = '<i class="fas fa-image"></i>';
                document.getElementById('imagem-preview').removeAttribute('data-base64');
            }
            document.getElementById('modal-produto').classList.add('active');
        }

        function fecharModalProduto() {
            document.getElementById('modal-produto').classList.remove('active');
            contexto.editandoProduto = null;
        }

        function previewImagem(event) {
            const file = event.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = (e) => {
                    const preview = document.getElementById('imagem-preview');
                    preview.innerHTML = `<img src="${e.target.result}">`;
                    preview.dataset.base64 = e.target.result;
                };
                reader.readAsDataURL(file);
            }
        }

        function criarCategoria() {
            const input = document.getElementById('nova-categoria');
            const categoria = input.value.trim();
            if (!categoria) return;
            if (!contexto.categorias.includes(categoria)) {
                contexto.categorias.push(categoria);
                contexto.categorias = normalizarCategorias(contexto.categorias);
                const local = JSON.parse(localStorage.getItem(storageKey('restaurante_config')) || '{}');
                local.categorias = contexto.categorias;
                localStorage.setItem(storageKey('restaurante_config'), JSON.stringify(local));
            }
            renderizarSelectCategorias(categoria);
            document.getElementById('produto-categoria').value = categoria;
            input.value = '';
        }

        async function salvarProduto() {
            const nome = document.getElementById('produto-nome').value;
            const categoria = document.getElementById('produto-categoria').value;
            const preco = parseFloat(document.getElementById('produto-preco').value);
            const descricao = document.getElementById('produto-descricao').value;
            const disponivel = document.getElementById('produto-disponivel').checked;
            const horarioInicio = document.getElementById('produto-horario-inicio').value || '';
            const horarioFim = document.getElementById('produto-horario-fim').value || '';
            const imagem = document.getElementById('imagem-preview').dataset.base64 || '';

            if (!nome || !preco) {
                alert('Preencha nome e preço');
                return;
            }

            const payload = {
                'token-acesso': contexto.token,
                nome,
                preco,
                categoria,
                descricao,
                imagem_base64: imagem,
                disponivel,
                horario_inicio: horarioInicio,
                horario_fim: horarioFim
            };

            try {
                let res;
                if (contexto.editandoProduto !== null) {
                    res = await fetch(`${API_URL}/api/admin/cardapio/${contexto.slug}/${contexto.editandoProduto}`, {
                        method: 'PATCH',
                        headers: {
                            'Content-Type': 'application/json',
                            'token-acesso': contexto.token
                        },
                        body: JSON.stringify({
                            nome,
                            preco,
                            categoria,
                            descricao,
                            imagem_base64: imagem,
                            disponivel,
                            horario_inicio: horarioInicio,
                            horario_fim: horarioFim
                        })
                    });
                } else {
                    res = await fetch(`${API_URL}/api/admin/cardapio`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                }

                if (res.ok) {
                    await carregarProdutos();
                    contexto.modoApi = true;
                } else {
                    throw new Error('Falha na API');
                }

                if (!contexto.modoApi) {
                    throw new Error('Modo local');
                }
                localStorage.setItem(storageKey('produtos'), JSON.stringify(contexto.produtos));
                renderizarProdutos();
                fecharModalProduto();
            } catch (e) {
                console.error('Erro ao salvar produto:', e);
                const idLocal = contexto.editandoProduto !== null ? contexto.editandoProduto : Date.now();
                const existente = contexto.produtos.findIndex(p => p.id === idLocal);
                const produtoLocal = { id: idLocal, nome, categoria, preco, descricao, imagem, disponivel, horario_inicio: horarioInicio, horario_fim: horarioFim };
                if (existente >= 0) contexto.produtos[existente] = produtoLocal;
                else contexto.produtos.push(produtoLocal);
                localStorage.setItem(storageKey('produtos'), JSON.stringify(contexto.produtos));
                contexto.modoApi = false;
                aplicarConfiguracaoNaTela();
                renderizarProdutos();
                fecharModalProduto();
            }
        }

        function deletarProduto(id) {
            if (confirm('Tem certeza?')) {
                (async () => {
                    try {
                        const res = await fetch(`${API_URL}/api/admin/cardapio/${contexto.slug}/${id}`, {
                            method: 'DELETE',
                            headers: { 'token-acesso': contexto.token }
                        });
                        if (!res.ok) {
                            throw new Error('Falha na API');
                        }
                    } catch (e) {
                        console.warn('Excluindo apenas localmente:', e.message);
                    }

                    contexto.produtos = contexto.produtos.filter(p => p.id !== id);
                    localStorage.setItem(storageKey('produtos'), JSON.stringify(contexto.produtos));
                    renderizarProdutos();
                })();
            }
        }

        function filtrarProdutos() {
            const filtro = document.getElementById('filtro-categoria').value.toLowerCase();
            const container = document.getElementById('produtos-container');
            container.innerHTML = contexto.produtos
                .filter(p => p.categoria.toLowerCase().includes(filtro) || p.nome.toLowerCase().includes(filtro))
                .filter(p => {
                    if (contexto.filtroProduto === 'ativos') return produtoDisponivelAgora(p);
                    if (contexto.filtroProduto === 'agendados') {
                        const { inicio, fim } = obterHorarioProduto(p);
                        return !!(inicio && fim);
                    }
                    if (contexto.filtroProduto === 'pausados') return p.disponivel === false || !produtoDisponivelAgora(p);
                    return true;
                })
                .map(p => {
                    const status = obterStatusProduto(p);
                    return `
                    <div class="product-card">
                        <div class="product-image">
                            ${p.imagem ? `<img src="${p.imagem}">` : '<div style="width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; background: #f1f5f9;"><i class="fas fa-image" style="font-size: 3rem; color: #cbd5e1;"></i></div>'}
                        </div>
                        <div class="product-info">
                            <div class="product-name">${p.nome}</div>
                            <div class="product-category">${p.categoria}</div>
                            <div class="product-status-row">
                                <span class="product-status-chip ${status.principal.tipo}"><i class="fas ${status.principal.icone}"></i> ${status.principal.texto}</span>
                                ${status.horario ? `<span class="product-status-chip info"><i class="fas fa-business-time"></i> ${status.horario}</span>` : ''}
                            </div>
                            <div class="product-price">R$ ${p.preco.toFixed(2).replace('.', ',')}</div>
                            <div class="product-actions">
                                <button class="btn btn-sm btn-themed-soft" onclick="abrirModalProduto(${p.id})"><i class="fas fa-edit"></i> Editar</button>
                                <button class="btn btn-danger btn-sm" onclick="deletarProduto(${p.id})"><i class="fas fa-trash"></i></button>
                            </div>
                        </div>
                    </div>
                `;
                }).join('');
        }

        function renderizarProdutos() {
            renderizarResumoProdutos();
            filtrarProdutos();
            document.getElementById('produtos-total').textContent = contexto.produtos.length;
        }

        // PEDIDOS
        async function carregarPedidos() {
            try {
                const res = await fetch(`${API_URL}/api/admin/pedidos/${contexto.slug}`, {
                    headers: { 'token-acesso': contexto.token }
                });
                if (res.ok) {
                    contexto.pedidos = await res.json();
                    await executarAutomacaoDelivery();
                } else {
                    contexto.pedidos = JSON.parse(localStorage.getItem(storageKey('pedidos')) || '[]');
                }
            } catch (e) {
                contexto.pedidos = JSON.parse(localStorage.getItem(storageKey('pedidos')) || '[]');
            }
        }

        async function despacharAutomaticamentePedidoPronto(pedido) {
            const falhas = contexto.automacaoFalhasPorPedido || {};
            const agora = Date.now();
            const ultimaFalha = Number(falhas[pedido.id] || 0);
            if (ultimaFalha && (agora - ultimaFalha) < 45000) {
                return false;
            }

            try {
                const res = await fetch(`${API_URL}/api/admin/pedidos/${contexto.slug}/${pedido.id}/despacho-automatico`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'token-acesso': contexto.token
                    },
                    body: JSON.stringify({
                        frontend_base_url: window.location.origin,
                        api_base_url: API_URL
                    })
                });

                if (!res.ok) {
                    falhas[pedido.id] = agora;
                    contexto.automacaoFalhasPorPedido = falhas;
                    return false;
                }

                delete falhas[pedido.id];
                contexto.automacaoFalhasPorPedido = falhas;
                return true;
            } catch (erro) {
                falhas[pedido.id] = agora;
                contexto.automacaoFalhasPorPedido = falhas;
                return false;
            }
        }

        async function executarAutomacaoDelivery() {
            if (!contexto.automacaoDeliveryAtiva || contexto.automacaoExecutando || !contexto.token) return;
            contexto.automacaoExecutando = true;

            let alterouFluxo = false;
            try {
                const deliveriesAbertos = (contexto.pedidos || []).filter(p => String(p.tipo_entrega || '').toLowerCase() === 'delivery');

                for (const pedido of deliveriesAbertos) {
                    const status = String(pedido.status || '').toLowerCase();

                    if (status === 'novo') {
                        await atualizarStatus(pedido.id, 'preparando', false);
                        alterouFluxo = true;
                        continue;
                    }

                    if (status === 'pronto') {
                        const despachou = await despacharAutomaticamentePedidoPronto(pedido);
                        if (despachou) {
                            alterouFluxo = true;
                        }
                    }
                }

                if (alterouFluxo) {
                    const res = await fetch(`${API_URL}/api/admin/pedidos/${contexto.slug}`, {
                        headers: { 'token-acesso': contexto.token }
                    });
                    if (res.ok) {
                        contexto.pedidos = await res.json();
                    }
                }
            } finally {
                contexto.automacaoExecutando = false;
            }
        }

        function pedidoPassaFiltro(pedido) {
            const status = (pedido.status || '').toLowerCase();
            if (contexto.filtroPedidos === 'abertos') {
                return ['novo', 'preparando', 'pronto', 'em_entrega'].includes(status);
            }
            if (contexto.filtroPedidos === 'entregues') {
                return status === 'entregue';
            }
            if (contexto.filtroPedidos === 'fechados') {
                return status === 'fechado';
            }
            return true;
        }

        function definirFiltroPedidos(filtro, event) {
            contexto.filtroPedidos = filtro;
            document.querySelectorAll('#filtros-pedidos-status .filter-chip').forEach(btn => btn.classList.remove('active'));
            event.currentTarget.classList.add('active');
            renderizarPedidos();
        }

        function formatarEnderecoEntrega(endereco = {}) {
            if (!endereco || typeof endereco !== 'object') return '';
            const linha1 = [endereco.rua, endereco.numero].filter(Boolean).join(', ');
            const linha2 = [endereco.bairro, endereco.cidade, endereco.uf].filter(Boolean).join(' - ');
            const linha3 = [endereco.complemento, endereco.referencia].filter(Boolean).join(' | ');
            return [linha1, linha2, linha3].filter(Boolean).join(' · ');
        }

        function formatarWhatsApp(valor = '') {
            const digitos = String(valor || '').replace(/\D/g, '');
            if (!digitos) return '-';
            if (digitos.length < 12) return digitos;
            return `+${digitos.slice(0, 2)} ${digitos.slice(2, 4)} ${digitos.slice(4)}`;
        }

        function montarLinkEntregador(entregadorToken, pedidoId) {
            if (!entregadorToken || !pedidoId) return '';
            const url = new URL('/entregador.html', window.location.origin);
            url.searchParams.set('slug', contexto.slug || '');
            url.searchParams.set('pedido', String(pedidoId));
            url.searchParams.set('token', String(entregadorToken));
            const apiNormalizada = String(API_URL || '').replace(/\/$/, '');
            const origemAtual = String(window.location.origin || '').replace(/\/$/, '');
            const apiEhExterna = !!apiNormalizada && apiNormalizada !== origemAtual;
            if (apiEhExterna) {
                url.searchParams.set('api', API_URL);
            }
            return url.toString();
        }

        async function copiarTextoClipboard(texto) {
            if (!texto) return false;
            try {
                await navigator.clipboard.writeText(texto);
                return true;
            } catch (_) {
                const input = document.createElement('textarea');
                input.value = texto;
                input.style.position = 'fixed';
                input.style.opacity = '0';
                document.body.appendChild(input);
                input.focus();
                input.select();
                const ok = document.execCommand('copy');
                document.body.removeChild(input);
                return !!ok;
            }
        }

        async function testarWhatsAppApiReal() {
            if (!contexto.slug || !contexto.token) {
                alert('Slug/token do admin não configurados.');
                return;
            }

            const telefone = prompt('Telefone para teste (somente números, ex: 5511999999999):');
            if (!telefone) return;

            const mensagemPadrao = `Teste de status do pedido - ${contexto.restaurante?.nome_unidade || 'Restaurante'}`;

            try {
                const res = await fetch(`${API_URL}/api/admin/restaurante/${contexto.slug}/whatsapp/teste`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'token-acesso': contexto.token
                    },
                    body: JSON.stringify({
                        telefone,
                        mensagem: mensagemPadrao
                    })
                });

                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    const detalhe = typeof data?.detail === 'string'
                        ? data.detail
                        : (data?.detail?.mensagem || 'Falha ao enviar teste WhatsApp');
                    throw new Error(detalhe);
                }

                alert('Mensagem de teste enviada com sucesso no WhatsApp real.');
            } catch (erro) {
                alert(`Erro no teste WhatsApp: ${erro.message || 'falha desconhecida'}`);
            }
        }

        function entregadorOnline(entregador) {
            if (!entregador?.ultima_atualizacao) return false;
            const diff = Date.now() - new Date(entregador.ultima_atualizacao).getTime();
            return diff <= 120000;
        }

        async function carregarEntregadores() {
            try {
                const res = await fetch(`${API_URL}/api/admin/entregadores/${contexto.slug}`, {
                    headers: { 'token-acesso': contexto.token }
                });
                if (res.ok) {
                    contexto.entregadores = await res.json();
                    localStorage.setItem(storageKey('entregadores'), JSON.stringify(contexto.entregadores));
                    return;
                }
            } catch (_) {}
            contexto.entregadores = JSON.parse(localStorage.getItem(storageKey('entregadores')) || '[]');
        }

        function renderizarEntregadores() {
            const container = document.getElementById('entregadores-container');
            if (!container) return;
            if (!contexto.entregadores.length) {
                container.innerHTML = '<div style="font-size:0.82rem;color:#64748b;padding:0.75rem;border:1px dashed #cbd5e1;border-radius:0.6rem;">Nenhum entregador cadastrado.</div>';
                atualizarPainelCorridaTempoReal();
                return;
            }

            container.innerHTML = contexto.entregadores.map(e => {
                const online = entregadorOnline(e);
                const temCoordenada = e.ultima_latitude !== null && e.ultima_longitude !== null && e.ultima_latitude !== undefined && e.ultima_longitude !== undefined;
                const linkMapa = temCoordenada
                    ? `https://www.google.com/maps?q=${encodeURIComponent(`${e.ultima_latitude},${e.ultima_longitude}`)}`
                    : '';
                return `
                    <div style="border:1px solid #dbe4ef;border-radius:0.75rem;padding:0.75rem;background:#fff;">
                        <div style="display:flex;justify-content:space-between;align-items:center;gap:0.7rem;">
                            <div>
                                <div style="font-size:0.9rem;font-weight:700;color:#1e293b;">${e.nome}</div>
                                <div style="font-size:0.76rem;color:#64748b;">WhatsApp: ${formatarWhatsApp(e.whatsapp)}</div>
                            </div>
                            <span style="font-size:0.72rem;font-weight:700;padding:0.2rem 0.55rem;border-radius:999px;${online ? 'background:#dcfce7;color:#166534;' : 'background:#fee2e2;color:#991b1b;'}">${online ? 'ONLINE' : 'OFFLINE'}</span>
                        </div>
                        <div style="margin-top:0.55rem;font-size:0.76rem;color:#475569;display:grid;gap:0.25rem;">
                            <div>Última atualização: ${e.ultima_atualizacao ? new Date(e.ultima_atualizacao).toLocaleString('pt-BR') : 'sem sinal'}</div>
                            <div>Precisão: ${e.ultima_precisao ? `${Number(e.ultima_precisao).toFixed(1)} m` : '-'}</div>
                        </div>
                        <div style="display:flex;gap:0.45rem;flex-wrap:wrap;margin-top:0.65rem;">
                            ${temCoordenada ? `<button class="btn btn-sm btn-secondary" onclick="window.open('${linkMapa}', '_blank')"><i class="fas fa-location-dot"></i> Ver no mapa</button>` : ''}
                            <button class="btn btn-sm ${e.ativo ? 'btn-danger' : 'btn-themed-soft'}" onclick="alternarEntregadorAtivo(${e.id}, ${!e.ativo})">${e.ativo ? 'Desativar' : 'Ativar'}</button>
                        </div>
                    </div>
                `;
            }).join('');

            atualizarPainelCorridaTempoReal();
        }

        function obterPedidosDeliveryAtivos() {
            return (contexto.pedidos || []).filter(p => {
                const tipo = String(p.tipo_entrega || '').toLowerCase();
                const status = String(p.status || '').toLowerCase();
                return tipo === 'delivery' && !['cancelado', 'entregue', 'fechado'].includes(status);
            });
        }

        function montarLinkClienteRastreio(pedidoId) {
            if (!pedidoId) return '';
            const url = new URL('/rastreio_entrega.html', window.location.origin);
            url.searchParams.set('slug', contexto.slug || '');
            url.searchParams.set('pedido', String(pedidoId));
            const apiNormalizada = String(API_URL || '').replace(/\/$/, '');
            const origemAtual = String(window.location.origin || '').replace(/\/$/, '');
            if (apiNormalizada && apiNormalizada !== origemAtual) {
                url.searchParams.set('api', API_URL);
            }
            return url.toString();
        }

        function distanciaKm(lat1, lon1, lat2, lon2) {
            const toRad = (v) => (v * Math.PI) / 180;
            const raio = 6371;
            const dLat = toRad(lat2 - lat1);
            const dLon = toRad(lon2 - lon1);
            const a = Math.sin(dLat / 2) ** 2
                + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
            const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
            return raio * c;
        }

        async function geocodificarEndereco(textoEndereco) {
            const texto = String(textoEndereco || '').trim();
            if (!texto) return null;

            const chave = texto.toLowerCase();
            if (contexto.geoCache[chave]) {
                return contexto.geoCache[chave];
            }

            try {
                const url = `https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(texto)}`;
                const res = await fetch(url, {
                    headers: {
                        'Accept': 'application/json',
                        'Accept-Language': 'pt-BR'
                    }
                });
                if (!res.ok) return null;
                const data = await res.json();
                if (!Array.isArray(data) || !data.length) return null;
                const ponto = {
                    lat: Number(data[0].lat),
                    lon: Number(data[0].lon)
                };
                if (Number.isNaN(ponto.lat) || Number.isNaN(ponto.lon)) return null;
                contexto.geoCache[chave] = ponto;
                return ponto;
            } catch (_) {
                return null;
            }
        }

        function renderizarMetricasCorrida({ pedido, entregador, online, distanciaAteDestino, ultimaAtualizacao }) {
            const metricas = document.getElementById('corrida-metricas');
            if (!metricas) return;

            const distanciaNumero = Number(String(distanciaAteDestino || '').replace(' km', '').replace(',', '.'));
            let velocidadeClasse = 'media';
            let velocidadeTexto = 'Ritmo normal';
            if (!Number.isNaN(distanciaNumero)) {
                if (distanciaNumero <= 1.2) {
                    velocidadeClasse = 'rapida';
                    velocidadeTexto = 'Chegada rápida';
                } else if (distanciaNumero > 3.5) {
                    velocidadeClasse = 'lenta';
                    velocidadeTexto = 'Pode demorar';
                }
            }

            metricas.innerHTML = `
                <div class="corrida-metrica">
                    <span>Pedido</span>
                    <strong>#${pedido?.id || '-'} · ${pedido?.cliente_nome || 'Cliente'}</strong>
                </div>
                <div class="corrida-metrica">
                    <span>Entregador</span>
                    <strong>${entregador?.nome || '-'}</strong>
                </div>
                <div class="corrida-metrica">
                    <span>Status rastreio</span>
                    <strong style="color:${online ? '#166534' : '#991b1b'};">${online ? 'ONLINE' : 'OFFLINE'}</strong>
                </div>
                <div class="corrida-metrica">
                    <span>Última atualização</span>
                    <strong>${ultimaAtualizacao || 'Sem atualização'}</strong>
                </div>
                <div class="corrida-metrica">
                    <span>Distância até destino</span>
                    <strong>${distanciaAteDestino || '-'}</strong>
                </div>
                <div class="corrida-metrica">
                    <span>Previsão</span>
                    <strong><span class="corrida-chip ${velocidadeClasse}"><i class="fas fa-stopwatch"></i>${velocidadeTexto}</span></strong>
                </div>
            `;
        }

        function renderizarEtapasCorrida(etapaAtual = 0) {
            const container = document.getElementById('corrida-etapas');
            if (!container) return;
            const etapas = ['Pedido aceito', 'Saiu para entrega', 'Próximo ao destino', 'Entregue'];
            container.innerHTML = etapas.map((nome, indice) => {
                const classe = indice < etapaAtual ? 'ativa' : (indice === etapaAtual ? 'atual' : '');
                return `<div class="corrida-etapa ${classe}">${nome}</div>`;
            }).join('');
        }

        function calcularEtapaPorDistancia(statusPedido, distanciaKmNumero) {
            const status = String(statusPedido || '').toLowerCase();
            if (status === 'entregue') return 3;
            if (Number.isNaN(distanciaKmNumero)) return 1;
            if (distanciaKmNumero <= 0.35) return 2;
            return 1;
        }

        function calcularEtaMinutos(distanciaKmNumero) {
            if (Number.isNaN(distanciaKmNumero)) return null;
            const velocidadeMediaKmH = 28;
            const minutos = Math.max(2, Math.round((distanciaKmNumero / velocidadeMediaKmH) * 60));
            return minutos;
        }

        function selecionarCorridaPedido(valor) {
            const pedidoId = Number(valor || 0) || null;
            contexto.corridaPedidoId = pedidoId;
            const pedido = (contexto.pedidos || []).find(p => Number(p.id) === Number(pedidoId));
            if (pedido?.entregador_id) {
                contexto.corridaEntregadorId = Number(pedido.entregador_id);
                const selectEntregador = document.getElementById('corrida-entregador-select');
                if (selectEntregador) {
                    selectEntregador.value = String(contexto.corridaEntregadorId);
                }
            }
            if (pedidoId) {
                atualizarMapaCorrida(false);
            }
        }

        function selecionarCorridaEntregador(valor) {
            const entregadorId = Number(valor || 0) || null;
            contexto.corridaEntregadorId = entregadorId;
            if (entregadorId) {
                atualizarMapaCorrida(contexto.corridaAutoSeguir);
            }
        }

        function toggleAutoSeguirCorrida(ativo) {
            contexto.corridaAutoSeguir = !!ativo;
            if (contexto.corridaAutoSeguir) {
                centralizarNoEntregador();
            }
        }

        function garantirMapaCorrida() {
            const target = document.getElementById('corrida-map');
            if (!target) return false;
            if (typeof L === 'undefined') {
                target.innerHTML = '<div style="padding:1rem;color:#64748b;">Mapa indisponível no momento.</div>';
                return false;
            }
            if (!contexto.mapaCorrida) {
                contexto.mapaCorrida = L.map(target).setView([-23.55052, -46.633308], 12);
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                    attribution: '&copy; OpenStreetMap contributors'
                }).addTo(contexto.mapaCorrida);
            }
            return true;
        }

        function atualizarPainelCorridaTempoReal() {
            const selectPedido = document.getElementById('corrida-pedido-select');
            const selectEntregador = document.getElementById('corrida-entregador-select');
            if (!selectPedido || !selectEntregador) return;

            const pedidosDelivery = obterPedidosDeliveryAtivos();
            const entregadoresAtivos = (contexto.entregadores || []).filter(e => e.ativo);

            if (!contexto.corridaPedidoId && pedidosDelivery.length) {
                contexto.corridaPedidoId = Number(pedidosDelivery[0].id);
            }
            if (!contexto.corridaEntregadorId && entregadoresAtivos.length) {
                contexto.corridaEntregadorId = Number(entregadoresAtivos[0].id);
            }

            if (contexto.corridaPedidoId && !pedidosDelivery.some(p => Number(p.id) === Number(contexto.corridaPedidoId))) {
                contexto.corridaPedidoId = pedidosDelivery.length ? Number(pedidosDelivery[0].id) : null;
            }

            const pedidoSelecionado = pedidosDelivery.find(p => Number(p.id) === Number(contexto.corridaPedidoId));
            if (pedidoSelecionado?.entregador_id && entregadoresAtivos.some(e => Number(e.id) === Number(pedidoSelecionado.entregador_id))) {
                contexto.corridaEntregadorId = Number(pedidoSelecionado.entregador_id);
            }

            if (contexto.corridaEntregadorId && !entregadoresAtivos.some(e => Number(e.id) === Number(contexto.corridaEntregadorId))) {
                contexto.corridaEntregadorId = entregadoresAtivos.length ? Number(entregadoresAtivos[0].id) : null;
            }

            selectPedido.innerHTML = pedidosDelivery.length
                ? pedidosDelivery.map(p => `<option value="${p.id}" ${Number(p.id) === Number(contexto.corridaPedidoId) ? 'selected' : ''}>#${p.id} · ${p.cliente_nome || 'Cliente'} · ${formatarEnderecoEntrega(p.endereco_entrega || {}) || 'sem endereço'}</option>`).join('')
                : '<option value="">Sem pedidos delivery ativos</option>';

            selectEntregador.innerHTML = entregadoresAtivos.length
                ? entregadoresAtivos.map(e => `<option value="${e.id}" ${Number(e.id) === Number(contexto.corridaEntregadorId) ? 'selected' : ''}>${e.nome}</option>`).join('')
                : '<option value="">Sem entregador ativo</option>';
        }

        async function vincularRastreioPedido(pedidoId, entregadorId) {
            if (!pedidoId) {
                alert('Selecione um pedido delivery para vincular rastreio.');
                return null;
            }
            if (!entregadorId) {
                alert('Selecione um entregador ativo para vincular rastreio.');
                return null;
            }

            if (!contexto.token) {
                throw new Error('Rastreio em tempo real exige API ativa e token de admin válido. Abra o painel com ?slug=...&token=...');
            }

            const res = await fetch(`${API_URL}/api/admin/pedidos/${contexto.slug}/${pedidoId}/rastreio`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                    'token-acesso': contexto.token
                },
                body: JSON.stringify({ entregador_id: Number(entregadorId) })
            });

            if (!res.ok) {
                const erro = await res.json().catch(() => ({}));
                throw new Error(erro.detail || 'Falha ao vincular rastreio');
            }

            const data = await res.json();
            const pedido = (contexto.pedidos || []).find(p => Number(p.id) === Number(pedidoId));
            if (pedido) {
                pedido.entregador_id = Number(entregadorId);
            }
            return data.link_entregador || montarLinkEntregador(data.token_rastreamento, pedidoId);
        }

        async function vincularRastreioSelecionado() {
            const pedidoId = Number(document.getElementById('corrida-pedido-select')?.value || 0) || null;
            const entregadorId = Number(document.getElementById('corrida-entregador-select')?.value || 0) || null;
            try {
                const link = await vincularRastreioPedido(pedidoId, entregadorId);
                if (!link) return;
                await copiarTextoClipboard(link);
                alert('Rastreio vinculado com sucesso. Link do entregador copiado.');
                renderizarPedidos();
            } catch (erro) {
                alert(erro.message || 'Não foi possível vincular o rastreio.');
            }
        }

        async function copiarLinkEntregadorSelecionado() {
            const pedidoId = Number(document.getElementById('corrida-pedido-select')?.value || 0) || null;
            const entregadorId = Number(document.getElementById('corrida-entregador-select')?.value || 0) || null;
            try {
                const link = await vincularRastreioPedido(pedidoId, entregadorId);
                if (!link) return;
                const ok = await copiarTextoClipboard(link);
                if (!ok) {
                    alert(`Link gerado:\n${link}`);
                    return;
                }
                alert('Link do entregador copiado com sucesso.');
                renderizarPedidos();
            } catch (erro) {
                alert(erro.message || 'Não foi possível copiar o link do entregador.');
            }
        }

        async function copiarPacoteCorridaSelecionado() {
            const pedidoId = Number(document.getElementById('corrida-pedido-select')?.value || 0) || null;
            if (!pedidoId) {
                alert('Selecione um pedido delivery para gerar o fluxo completo.');
                return;
            }
            await copiarPacoteCorridaPorId(pedidoId);
        }

        async function iniciarAcompanhamentoCorrida() {
            const pedidoId = Number(document.getElementById('corrida-pedido-select')?.value || 0) || null;
            const entregadorId = Number(document.getElementById('corrida-entregador-select')?.value || 0) || null;

            if (!pedidoId) {
                alert('Selecione um pedido delivery para acompanhar.');
                return;
            }
            if (!entregadorId) {
                alert('Selecione um entregador ativo para acompanhar.');
                return;
            }

            contexto.corridaPedidoId = pedidoId;
            contexto.corridaEntregadorId = entregadorId;
            await atualizarMapaCorrida(true);
        }

        function abrirRotaCorridaAtual() {
            const pedido = (contexto.pedidos || []).find(p => Number(p.id) === Number(contexto.corridaPedidoId));
            if (!pedido) {
                alert('Selecione um pedido delivery para abrir a rota.');
                return;
            }
            const enderecoDestino = formatarEnderecoEntrega(pedido.endereco_entrega || {});
            if (!enderecoDestino) {
                alert('Pedido sem endereço de entrega.');
                return;
            }
            const origem = (contexto.restaurante.delivery_endereco_origem || '').trim();
            const entregador = (contexto.entregadores || []).find(e => Number(e.id) === Number(contexto.corridaEntregadorId));
            const origemPreferida = (entregador?.ultima_latitude !== null && entregador?.ultima_longitude !== null && entregador?.ultima_latitude !== undefined && entregador?.ultima_longitude !== undefined)
                ? `${entregador.ultima_latitude},${entregador.ultima_longitude}`
                : origem;

            if (!origemPreferida) {
                alert('Configure o endereço de saída do restaurante para gerar a rota.');
                return;
            }

            const rota = `https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(origemPreferida)}&destination=${encodeURIComponent(enderecoDestino)}&travelmode=driving`;
            window.open(rota, '_blank');
        }

        async function centralizarNoEntregador() {
            if (!garantirMapaCorrida()) return;

            if (!contexto.camadaCorrida) {
                await iniciarAcompanhamentoCorrida();
            }

            const entregador = (contexto.entregadores || []).find(e => Number(e.id) === Number(contexto.corridaEntregadorId));
            if (!entregador) {
                alert('Selecione um entregador para centralizar.');
                return;
            }

            const temLocal = entregador.ultima_latitude !== null
                && entregador.ultima_longitude !== null
                && entregador.ultima_latitude !== undefined
                && entregador.ultima_longitude !== undefined;

            if (!temLocal) {
                alert('Este entregador ainda não enviou localização.');
                return;
            }

            const lat = Number(entregador.ultima_latitude);
            const lon = Number(entregador.ultima_longitude);
            if (Number.isNaN(lat) || Number.isNaN(lon)) {
                alert('Localização inválida para centralizar no mapa.');
                return;
            }

            contexto.mapaCorrida.setView([lat, lon], 16, { animate: true, duration: 0.5 });
        }

        async function atualizarMapaCorrida(centralizar = false) {
            if (!garantirMapaCorrida()) return;

            const pedido = (contexto.pedidos || []).find(p => Number(p.id) === Number(contexto.corridaPedidoId));
            const entregador = (contexto.entregadores || []).find(e => Number(e.id) === Number(contexto.corridaEntregadorId));
            if (!pedido || !entregador) {
                renderizarMetricasCorrida({ pedido: null, entregador: null, online: false, distanciaAteDestino: null, ultimaAtualizacao: null });
                return;
            }

            const origemTexto = (contexto.restaurante.delivery_endereco_origem || '').trim();
            const destinoTexto = formatarEnderecoEntrega(pedido.endereco_entrega || {});

            const [origemCoord, destinoCoord] = await Promise.all([
                geocodificarEndereco(origemTexto),
                geocodificarEndereco(destinoTexto)
            ]);

            const entregadorCoord = (entregador.ultima_latitude !== null && entregador.ultima_longitude !== null && entregador.ultima_latitude !== undefined && entregador.ultima_longitude !== undefined)
                ? { lat: Number(entregador.ultima_latitude), lon: Number(entregador.ultima_longitude) }
                : null;

            if (contexto.camadaCorrida) {
                contexto.mapaCorrida.removeLayer(contexto.camadaCorrida);
            }
            contexto.camadaCorrida = L.layerGroup().addTo(contexto.mapaCorrida);

            const pontos = [];
            if (origemCoord) {
                L.circleMarker([origemCoord.lat, origemCoord.lon], { radius: 8, color: '#1d4ed8', weight: 2, fillColor: '#3b82f6', fillOpacity: 0.9 })
                    .bindPopup('Origem do restaurante')
                    .addTo(contexto.camadaCorrida);
                pontos.push([origemCoord.lat, origemCoord.lon]);
            }
            if (destinoCoord) {
                L.circleMarker([destinoCoord.lat, destinoCoord.lon], { radius: 8, color: '#b91c1c', weight: 2, fillColor: '#ef4444', fillOpacity: 0.9 })
                    .bindPopup(`Destino do pedido #${pedido.id}`)
                    .addTo(contexto.camadaCorrida);
                pontos.push([destinoCoord.lat, destinoCoord.lon]);
            }
            if (entregadorCoord) {
                L.circleMarker([entregadorCoord.lat, entregadorCoord.lon], { radius: 8, color: '#166534', weight: 2, fillColor: '#22c55e', fillOpacity: 0.92 })
                    .bindPopup(`Entregador: ${entregador.nome}`)
                    .addTo(contexto.camadaCorrida);
                pontos.push([entregadorCoord.lat, entregadorCoord.lon]);
            }

            if (origemCoord && destinoCoord) {
                L.polyline(
                    [[origemCoord.lat, origemCoord.lon], [destinoCoord.lat, destinoCoord.lon]],
                    { color: '#64748b', dashArray: '6,6', weight: 3 }
                ).addTo(contexto.camadaCorrida);
            }
            if (entregadorCoord && destinoCoord) {
                L.polyline(
                    [[entregadorCoord.lat, entregadorCoord.lon], [destinoCoord.lat, destinoCoord.lon]],
                    { color: '#16a34a', weight: 4 }
                ).addTo(contexto.camadaCorrida);
            }

            if (pontos.length && (centralizar || !contexto.mapaCorrida._corridaInicializada)) {
                const bounds = L.latLngBounds(pontos);
                contexto.mapaCorrida.fitBounds(bounds.pad(0.2));
                contexto.mapaCorrida._corridaInicializada = true;
            }

            if (contexto.corridaAutoSeguir && entregadorCoord) {
                contexto.mapaCorrida.setView([entregadorCoord.lat, entregadorCoord.lon], 16, { animate: true, duration: 0.45 });
            }

            const online = entregadorOnline(entregador);
            const distanciaNumero = (entregadorCoord && destinoCoord)
                ? distanciaKm(entregadorCoord.lat, entregadorCoord.lon, destinoCoord.lat, destinoCoord.lon)
                : NaN;
            const distanciaTexto = Number.isNaN(distanciaNumero) ? null : `${distanciaNumero.toFixed(2)} km`;
            const etaMin = calcularEtaMinutos(distanciaNumero);
            const ultimaAtualizacao = entregador.ultima_atualizacao
                ? new Date(entregador.ultima_atualizacao).toLocaleString('pt-BR')
                : null;
            const etapaAtual = calcularEtapaPorDistancia(pedido.status, distanciaNumero);

            renderizarEtapasCorrida(etapaAtual);

            renderizarMetricasCorrida({
                pedido,
                entregador,
                online,
                distanciaAteDestino: etaMin ? `${distanciaTexto || '-'} · ETA ${etaMin} min` : distanciaTexto,
                ultimaAtualizacao
            });
        }

        async function cadastrarEntregador() {
            const nome = (document.getElementById('entregador-nome')?.value || '').trim();
            const whatsapp = (document.getElementById('entregador-whatsapp')?.value || '').replace(/\D/g, '');

            if (nome.length < 2) {
                alert('Informe um nome válido para o entregador.');
                return;
            }
            if (whatsapp.length < 8) {
                alert('Informe um WhatsApp válido do entregador.');
                return;
            }

            if (!contexto.token) {
                const novo = {
                    id: Date.now(),
                    nome,
                    whatsapp,
                    token_rastreamento: String(Date.now()),
                    ativo: true,
                    ultima_latitude: null,
                    ultima_longitude: null,
                    ultima_precisao: null,
                    ultima_atualizacao: null
                };
                contexto.entregadores.push(novo);
                localStorage.setItem(storageKey('entregadores'), JSON.stringify(contexto.entregadores));
                document.getElementById('entregador-nome').value = '';
                document.getElementById('entregador-whatsapp').value = '';
                renderizarEntregadores();
                alert('Entregador salvo localmente (sem token/API). Rastreamento em tempo real só funciona com API e token válidos no admin.');
                return;
            }

            try {
                const res = await fetch(`${API_URL}/api/admin/entregadores/${contexto.slug}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'token-acesso': contexto.token
                    },
                    body: JSON.stringify({ nome, whatsapp })
                });
                if (!res.ok) {
                    const erro = await res.json().catch(() => ({}));
                    throw new Error(erro.detail || 'Falha ao cadastrar entregador');
                }
                document.getElementById('entregador-nome').value = '';
                document.getElementById('entregador-whatsapp').value = '';
                await carregarEntregadores();
                renderizarEntregadores();
            } catch (erro) {
                const novo = {
                    id: Date.now(),
                    nome,
                    whatsapp,
                    token_rastreamento: String(Date.now()),
                    ativo: true,
                    ultima_latitude: null,
                    ultima_longitude: null,
                    ultima_precisao: null,
                    ultima_atualizacao: null
                };
                contexto.entregadores.push(novo);
                localStorage.setItem(storageKey('entregadores'), JSON.stringify(contexto.entregadores));
                document.getElementById('entregador-nome').value = '';
                document.getElementById('entregador-whatsapp').value = '';
                renderizarEntregadores();
                alert(`API indisponível (${erro.message || 'erro desconhecido'}). Entregador salvo localmente; rastreio em tempo real ficará indisponível até a API voltar.`);
            }
        }

        async function alternarEntregadorAtivo(entregadorId, ativo) {
            try {
                const res = await fetch(`${API_URL}/api/admin/entregadores/${contexto.slug}/${entregadorId}`, {
                    method: 'PATCH',
                    headers: {
                        'Content-Type': 'application/json',
                        'token-acesso': contexto.token
                    },
                    body: JSON.stringify({ ativo })
                });
                if (!res.ok) {
                    throw new Error('Falha ao atualizar entregador');
                }
            } catch (_) {
                const local = contexto.entregadores.find(e => Number(e.id) === Number(entregadorId));
                if (local) local.ativo = !!ativo;
            }
            await carregarEntregadores();
            renderizarEntregadores();
        }

        function abrirRotaWhatsApp(pedido, entregadorId = null) {
            const entregador = contexto.entregadores.find(e => Number(e.id) === Number(entregadorId) && e.ativo);
            const telefone = (entregador?.whatsapp || contexto.restaurante.delivery_whatsapp_entregador || '').replace(/\D/g, '');
            if (!telefone) {
                alert('Configure o WhatsApp do entregador em Delivery ou selecione um entregador cadastrado.');
                return;
            }
            const origem = (contexto.restaurante.delivery_endereco_origem || '').trim();
            if (!origem) {
                alert('Configure o endereço de saída do restaurante em Delivery.');
                return;
            }
            const enderecoTexto = formatarEnderecoEntrega(pedido.endereco_entrega || {});
            if (!enderecoTexto) {
                alert('Este pedido não possui endereço de entrega.');
                return;
            }

            const rota = `https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(origem)}&destination=${encodeURIComponent(enderecoTexto)}&travelmode=driving`;
            const texto = [
                `Entrega pedido #${pedido.id}`,
                `Entregador: ${entregador?.nome || 'Padrão'}`,
                `Cliente: ${pedido.cliente_nome || 'Não informado'}`,
                `Telefone cliente: ${pedido.cliente_telefone || 'Não informado'}`,
                `Endereço: ${enderecoTexto}`,
                `Rota: ${rota}`
            ].join('\n');

            window.open(`https://wa.me/${telefone}?text=${encodeURIComponent(texto)}`, '_blank');
        }

        function abrirRotaWhatsAppPorId(pedidoId) {
            const pedido = contexto.pedidos.find(p => Number(p.id) === Number(pedidoId));
            if (!pedido) {
                alert('Pedido não encontrado para gerar rota.');
                return;
            }
            const entregadorId = Number(document.getElementById(`pedido-entregador-${pedidoId}`)?.value || 0) || null;
            abrirRotaWhatsApp(pedido, entregadorId);
        }

        async function vincularRastreioPorId(pedidoId) {
            const entregadorId = Number(document.getElementById(`pedido-entregador-${pedidoId}`)?.value || 0) || null;
            try {
                const link = await vincularRastreioPedido(Number(pedidoId), entregadorId);
                if (!link) return;
                alert('Pedido vinculado ao entregador com sucesso.');
                renderizarPedidos();
            } catch (erro) {
                alert(erro.message || 'Não foi possível vincular rastreio para o pedido.');
            }
        }

        async function copiarLinkEntregadorPorId(pedidoId) {
            const entregadorId = Number(document.getElementById(`pedido-entregador-${pedidoId}`)?.value || 0) || null;
            try {
                const link = await vincularRastreioPedido(Number(pedidoId), entregadorId);
                if (!link) return;
                const ok = await copiarTextoClipboard(link);
                if (!ok) {
                    alert(`Link do entregador:\n${link}`);
                    return;
                }
                alert('Link do entregador copiado. Envie esse link para ele abrir no celular.');
                renderizarPedidos();
            } catch (erro) {
                alert(erro.message || 'Não foi possível gerar/copiar o link do entregador.');
            }
        }

        async function copiarLinkClientePorId(pedidoId) {
            const link = montarLinkClienteRastreio(pedidoId);
            if (!link) {
                alert('Não foi possível gerar o link de rastreio para o cliente.');
                return;
            }
            const ok = await copiarTextoClipboard(link);
            if (!ok) {
                alert(`Link de rastreio do cliente:\n${link}`);
                return;
            }
            alert('Link de rastreio do cliente copiado.');
        }

        function normalizarTelefoneWhatsApp(telefone = '') {
            const digitos = String(telefone || '').replace(/\D/g, '');
            if (!digitos) return '';
            if (digitos.length === 10 || digitos.length === 11) return `55${digitos}`;
            return digitos;
        }

        async function enviarRastreioClienteWhatsAppPorId(pedidoId) {
            const pedido = contexto.pedidos.find(p => Number(p.id) === Number(pedidoId));
            if (!pedido) {
                alert('Pedido não encontrado para envio ao cliente.');
                return;
            }

            const telefoneCliente = normalizarTelefoneWhatsApp(pedido.cliente_telefone || '');
            if (!telefoneCliente) {
                alert('Telefone do cliente não encontrado neste pedido.');
                return;
            }

            const entregadorId = Number(document.getElementById(`pedido-entregador-${pedidoId}`)?.value || 0)
                || Number(pedido.entregador_id || 0)
                || Number((contexto.entregadores || []).find(e => e.ativo)?.id || 0)
                || null;

            if (!entregadorId) {
                alert('Selecione um entregador ativo antes de enviar o rastreio ao cliente.');
                return;
            }

            try {
                await vincularRastreioPedido(Number(pedidoId), Number(entregadorId));
            } catch (erro) {
                alert(erro.message || 'Não foi possível vincular o rastreio antes do envio ao cliente.');
                return;
            }

            const linkCliente = montarLinkClienteRastreio(Number(pedidoId));
            const nomeCliente = String(pedido.cliente_nome || '').trim();
            const nomeRestaurante = String(contexto?.restaurante?.nome_unidade || 'nosso restaurante').trim();
            const mensagem = [
                'confira seu pedido',
                nomeCliente ? `Olá, ${nomeCliente}!` : 'Olá!',
                `Seu pedido #${pedido.id} já está em rota com o ${nomeRestaurante}.`,
                'Acompanhe em tempo real pelo link abaixo:',
                `${linkCliente}`
            ].join('\n');

            window.open(`https://wa.me/${telefoneCliente}?text=${encodeURIComponent(mensagem)}`, '_blank');
            alert('WhatsApp aberto com a mensagem de rastreio do cliente.');
            renderizarPedidos();
        }

        async function enviarRastreioClienteWhatsAppSelecionado() {
            const pedidoId = Number(document.getElementById('corrida-pedido-select')?.value || 0) || null;
            if (!pedidoId) {
                alert('Selecione um pedido delivery para enviar no WhatsApp do cliente.');
                return;
            }
            await enviarRastreioClienteWhatsAppPorId(pedidoId);
        }

        async function copiarPacoteCorridaPorId(pedidoId) {
            const pedido = contexto.pedidos.find(p => Number(p.id) === Number(pedidoId));
            if (!pedido) {
                alert('Pedido não encontrado para gerar pacote da corrida.');
                return;
            }

            const entregadorId = Number(document.getElementById(`pedido-entregador-${pedidoId}`)?.value || 0)
                || Number(pedido.entregador_id || 0)
                || Number((contexto.entregadores || []).find(e => e.ativo)?.id || 0)
                || null;

            if (!entregadorId) {
                alert('Selecione um entregador ativo para gerar o pacote da corrida.');
                return;
            }

            try {
                const linkEntregador = await vincularRastreioPedido(Number(pedidoId), Number(entregadorId));
                const linkCliente = montarLinkClienteRastreio(Number(pedidoId));
                const endereco = formatarEnderecoEntrega(pedido.endereco_entrega || {}) || 'Não informado';
                const entregador = (contexto.entregadores || []).find(e => Number(e.id) === Number(entregadorId));

                const pacote = [
                    `Pedido #${pedido.id}`,
                    `Cliente: ${pedido.cliente_nome || 'Não informado'}`,
                    `Telefone cliente: ${pedido.cliente_telefone || 'Não informado'}`,
                    `Endereço entrega: ${endereco}`,
                    `Entregador: ${entregador?.nome || 'Padrão'}`,
                    `Link MOTOboy: ${linkEntregador || '-'}`,
                    `Link CLIENTE (tempo real): ${linkCliente || '-'}`
                ].join('\n');

                const ok = await copiarTextoClipboard(pacote);
                if (!ok) {
                    alert(`Pacote da corrida:\n${pacote}`);
                    return;
                }

                alert('Pacote da corrida copiado. Envie o endereço+link do motoboy para o entregador e o link de rastreio para o cliente.');
                renderizarPedidos();
            } catch (erro) {
                alert(erro.message || 'Não foi possível gerar o pacote da corrida.');
            }
        }

        async function monitorarCorridaPorPedido(pedidoId) {
            const pedido = contexto.pedidos.find(p => Number(p.id) === Number(pedidoId));
            if (!pedido) {
                alert('Pedido não encontrado para monitoramento.');
                return;
            }

            if (!contexto.token) {
                alert('Para rastreio real, abra o admin com token válido (?slug=...&token=...).');
                return;
            }

            const entregadorIdSelecionado = Number(document.getElementById(`pedido-entregador-${pedidoId}`)?.value || 0) || null;
            const entregadorId = entregadorIdSelecionado
                || Number(pedido.entregador_id || 0)
                || Number((contexto.entregadores || []).find(e => e.ativo)?.id || 0)
                || null;

            if (!entregadorId) {
                alert('Selecione um entregador ativo para rastrear a corrida.');
                return;
            }

            try {
                await vincularRastreioPedido(Number(pedidoId), Number(entregadorId));
            } catch (erro) {
                alert(erro.message || 'Não foi possível vincular o entregador para rastreio.');
                return;
            }

            contexto.corridaPedidoId = Number(pedidoId);
            contexto.corridaEntregadorId = Number(entregadorId);

            mudarSecao('rastrear-pedidos');
            atualizarPainelCorridaTempoReal();
            await iniciarAcompanhamentoCorrida();

            const entregador = (contexto.entregadores || []).find(e => Number(e.id) === Number(entregadorId));
            if (!entregador?.ultima_atualizacao) {
                alert('Corrida aberta. Agora envie o link para o entregador iniciar o rastreio no celular.');
            }
        }

        function renderizarPedidos() {
            const container = document.getElementById('pedidos-container');
            const pedidosFiltrados = [...contexto.pedidos]
                .filter(pedidoPassaFiltro)
                .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
                .slice(0, 20)
            if (!pedidosFiltrados.length) {
                container.innerHTML = `<div class="card" style="padding: 1rem; color:#64748b;">Nenhum pedido encontrado para o filtro selecionado.</div>`;
                atualizarPainelCorridaTempoReal();
                return;
            }

            const pedidosDelivery = pedidosFiltrados.filter(p => String(p.tipo_entrega || '').toLowerCase() === 'delivery');
            const pedidosSalao = pedidosFiltrados.filter(p => String(p.tipo_entrega || '').toLowerCase() !== 'delivery');

            const renderizarCardPedido = (p) => {
                const tipoEntrega = (p.tipo_entrega || 'mesa').toLowerCase();
                const ehDelivery = tipoEntrega === 'delivery';
                const enderecoTexto = formatarEnderecoEntrega(p.endereco_entrega || {});
                const corFluxo = ehDelivery ? '#3b82f6' : '#10b981';
                const chipFluxoBg = ehDelivery ? '#dbeafe' : '#dcfce7';
                const chipFluxoTxt = ehDelivery ? '#1d4ed8' : '#166534';
                const opcoesEntregador = contexto.entregadores
                    .filter(e => e.ativo)
                    .map(e => `<option value="${e.id}" ${Number(e.id) === Number(p.entregador_id) ? 'selected' : ''}>${e.nome}</option>`)
                    .join('');
                return `
                    <div class="card pedido-card" style="border-left: 4px solid ${corFluxo}; padding: 1rem;">
                        <div class="pedido-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                            <div>
                                <div style="font-weight: 700; font-size: 1.1rem; color: #1e293b; display:flex; align-items:center; gap:0.45rem; flex-wrap:wrap;">
                                    <span>${ehDelivery ? 'Delivery' : `Mesa ${p.mesa}`}</span>
                                    <span style="display:inline-flex;align-items:center;padding:0.2rem 0.5rem;border-radius:999px;background:${chipFluxoBg};color:${chipFluxoTxt};font-size:0.7rem;font-weight:800;">${ehDelivery ? 'DELIVERY' : 'SALÃO/BALCÃO'}</span>
                                </div>
                                <div class="pedido-data" style="font-size: 0.75rem; color: #64748b;">${new Date(p.created_at).toLocaleString('pt-BR')}</div>
                            </div>
                            <div class="badge badge-${p.status}">${p.status.toUpperCase()}</div>
                        </div>
                        ${ehDelivery ? `
                            <div style="background:#eff6ff;border:1px solid #bfdbfe;padding:0.65rem;border-radius:0.5rem;margin-bottom:0.75rem;font-size:0.84rem;color:#1e3a8a;">
                                <div><strong>Cliente:</strong> ${p.cliente_nome || 'Não informado'}</div>
                                <div><strong>Telefone:</strong> ${p.cliente_telefone || 'Não informado'}</div>
                                <div><strong>Endereço:</strong> ${enderecoTexto || 'Não informado'}</div>
                            </div>
                        ` : ''}
                        <div style="background: #f8fafc; padding: 0.75rem; border-radius: 0.5rem; margin-bottom: 0.75rem; font-size: 0.875rem;">
                            ${p.itens.map(i => `<div>${i.quantidade}x ${i.nome} - R$ ${(i.quantidade * i.preco_unitario).toFixed(2).replace('.', ',')}</div>`).join('')}
                        </div>
                        <div class="pedido-total-row" style="display: flex; justify-content: space-between; align-items: center;">
                            <div style="font-weight: 700; font-size: 1.25rem; color: #1e293b;">R$ ${p.total.toFixed(2).replace('.', ',')}</div>
                            <span class="pedido-resumo" style="font-size:0.78rem;color:#64748b;font-weight:700;">Status: ${String(p.status || '').toUpperCase()}${p.forma_pagamento ? ` · ${String(p.forma_pagamento).toUpperCase()}` : ''}</span>
                        </div>
                        ${ehDelivery ? `
                            <div class="pedido-entrega-acoes" style="display:flex;gap:0.45rem;align-items:center;margin-top:0.65rem;flex-wrap:wrap;">
                                <select class="form-input" id="pedido-entregador-${p.id}" style="min-width:210px;max-width:320px;">
                                    <option value="">Entregador padrão</option>
                                    ${opcoesEntregador}
                                </select>
                                <button class="btn btn-sm btn-themed-soft" onclick="vincularRastreioPorId(${p.id})"><i class="fas fa-link"></i> Vincular rastreio</button>
                                <button class="btn btn-sm btn-secondary" onclick="copiarLinkEntregadorPorId(${p.id})"><i class="fas fa-copy"></i> Copiar link entregador</button>
                            </div>
                        ` : ''}
                        <div class="pedido-status-acoes" style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-top:0.75rem;">
                            <button class="btn btn-sm btn-secondary" onclick="atualizarStatus(${p.id}, 'preparando')"><i class="fas fa-fire-burner"></i> Preparando</button>
                            <button class="btn btn-sm btn-themed-soft" onclick="atualizarStatus(${p.id}, 'pronto')"><i class="fas fa-bell-concierge"></i> Pronto</button>
                            ${ehDelivery ? `<button class="btn btn-sm btn-themed-soft" onclick="atualizarStatus(${p.id}, 'em_entrega')"><i class="fas fa-motorcycle"></i> Em entrega</button>` : ''}
                            <button class="btn btn-sm btn-primary" onclick="atualizarStatus(${p.id}, 'entregue')"><i class="fas fa-check"></i> Entregue</button>
                            ${ehDelivery ? `<button class="btn btn-sm btn-themed-soft" onclick="monitorarCorridaPorPedido(${p.id})"><i class="fas fa-map-location-dot"></i> Rastrear entregador</button>` : ''}
                            ${ehDelivery ? `<button class="btn btn-sm btn-secondary" onclick="copiarLinkClientePorId(${p.id})"><i class="fas fa-share-nodes"></i> Link cliente</button>` : ''}
                            ${ehDelivery ? `<button class="btn btn-sm btn-secondary" onclick="copiarPacoteCorridaPorId(${p.id})"><i class="fas fa-paper-plane"></i> Fluxo completo</button>` : ''}
                            ${ehDelivery ? `<button class="btn btn-sm btn-secondary" onclick="enviarRastreioClienteWhatsAppPorId(${p.id})"><i class="fab fa-whatsapp"></i> Disparar cliente</button>` : ''}
                            ${ehDelivery ? `<button class="btn btn-sm btn-secondary" onclick="abrirRotaWhatsAppPorId(${p.id})"><i class="fab fa-whatsapp"></i> Enviar rota WhatsApp</button>` : ''}
                        </div>
                    </div>
                `;
            };

            const renderizarGrupo = (titulo, descricao, pedidos, corFundo, corBorda, corTitulo, corDescricao, corBadgeFundo, corBadgeTexto) => {
                const conteudo = pedidos.length
                    ? `<div style="display:grid;gap:0.75rem;">${pedidos.map(renderizarCardPedido).join('')}</div>`
                    : `<div style="padding:0.85rem;border:1px dashed #dbe4ef;border-radius:0.6rem;color:#64748b;background:#fff;">Nenhum pedido neste fluxo para o filtro atual.</div>`;
                return `
                    <div class="card" style="border:1px solid ${corBorda}; background:${corFundo}; padding:1rem;">
                        <div style="display:flex;align-items:center;justify-content:space-between;gap:0.75rem;margin-bottom:0.75rem;">
                            <div>
                                <div style="font-weight:800;font-size:1rem;color:${corTitulo};">${titulo}</div>
                                <div style="font-size:0.76rem;color:${corDescricao};">${descricao}</div>
                            </div>
                            <span class="badge" style="background:${corBadgeFundo};color:${corBadgeTexto};border:1px solid ${corBorda};font-weight:800;">${pedidos.length}</span>
                        </div>
                        ${conteudo}
                    </div>
                `;
            };

            container.innerHTML = `
                ${renderizarGrupo('Salão / Balcão', 'Pedidos de mesa e atendimento local', pedidosSalao, '#f0fdf4', '#86efac', '#166534', '#15803d', '#dcfce7', '#166534')}
                ${renderizarGrupo('Delivery', 'Pedidos de entrega com rastreio', pedidosDelivery, '#eff6ff', '#93c5fd', '#1d4ed8', '#1e40af', '#dbeafe', '#1d4ed8')}
            `;

            atualizarPainelCorridaTempoReal();
        }

        async function atualizarStatus(pedidoId, status, atualizarTela = true, formaPagamento = null) {
            try {
                const payload = { status };
                if (formaPagamento) {
                    payload.forma_pagamento = formaPagamento;
                }
                const res = await fetch(`${API_URL}/api/admin/pedidos/${contexto.slug}/${pedidoId}/status`, {
                    method: 'PATCH',
                    headers: {
                        'Content-Type': 'application/json',
                        'token-acesso': contexto.token
                    },
                    body: JSON.stringify(payload)
                });
                if (!res.ok) {
                    throw new Error('Falha na API ao atualizar status');
                }
            } catch (e) {
                const pedidoLocal = contexto.pedidos.find(p => p.id === pedidoId);
                if (pedidoLocal) {
                    pedidoLocal.status = status;
                    if (formaPagamento) pedidoLocal.forma_pagamento = formaPagamento;
                }
            }

            if (atualizarTela) {
                await carregarPedidos();
                renderizarPedidos();
                renderizarMesas();
                atualizarKPIsPedidos();
            }
        }

        // MESAS
        async function carregarMesas() {
            const quantidade = contexto.restaurante.total_mesas || 10;
            contexto.mesas = Array.from({ length: quantidade }, (_, indice) => {
                const numero = indice + 1;
                return { numero };
            });
            renderizarSeletorMesaPublica();
        }

        function renderizarMesas() {
            const container = document.getElementById('mesas-container');
            const pedidosAbertosPorMesa = contexto.pedidos
                .filter(p => ['novo', 'preparando', 'pronto', 'em_entrega'].includes((p.status || '').toLowerCase()))
                .reduce((acc, pedido) => {
                    const numeroMesa = Number(pedido.mesa || 0);
                    if (!numeroMesa) return acc;
                    if (!acc[numeroMesa]) {
                        acc[numeroMesa] = { quantidade: 0, total: 0 };
                    }
                    acc[numeroMesa].quantidade += 1;
                    acc[numeroMesa].total += Number(pedido.total || 0);
                    return acc;
                }, {});

            const ocupadas = contexto.mesas.filter(m => !!pedidosAbertosPorMesa[m.numero]).length;
            document.getElementById('mesas-ocupadas').textContent = `${ocupadas}/${contexto.mesas.length}`;

            container.innerHTML = contexto.mesas.map(m => {
                const resumo = pedidosAbertosPorMesa[m.numero];
                const ocupada = !!resumo;
                const subtitulo = ocupada
                    ? `🟡 ${resumo.quantidade} pedido(s) em andamento · R$ ${resumo.total.toFixed(2).replace('.', ',')}`
                    : '🟢 Disponível';

                const totalMesa = contexto.pedidos
                    .filter(p => Number(p.mesa || 0) === m.numero && (p.status || '').toLowerCase() !== 'cancelado')
                    .reduce((sum, pedido) => sum + Number(pedido.total || 0), 0);

                return `
                <div class="card" style="padding: 1.5rem; text-align: center; background: ${ocupada ? '#fffbeb' : '#fff'}; border: 2px solid ${ocupada ? '#fbbf24' : '#e2e8f0'};">
                    <i class="fas fa-chair" style="font-size: 2rem; color: ${ocupada ? '#d97706' : '#94a3b8'}; margin-bottom: 0.5rem;"></i>
                    <div style="font-weight: 700; font-size: 1.25rem; color: #1e293b;">Mesa ${m.numero}</div>
                    <div style="font-size: 0.875rem; color: #64748b; margin-top: 0.25rem;">${subtitulo}</div>
                    <div style="font-size: 0.9rem; color:#1e293b; margin-top:0.45rem; font-weight:700;">Total da mesa: R$ ${totalMesa.toFixed(2).replace('.', ',')}</div>
                    <button class="btn btn-themed-soft btn-sm" style="margin-top:0.7rem;" onclick="abrirResumoMesa(${m.numero})"><i class="fas fa-file-invoice-dollar"></i> Ver conta</button>
                </div>
            `;
            }).join('');
        }

        function obterPedidosMesa(numeroMesa) {
            return contexto.pedidos
                .filter(p => Number(p.mesa || 0) === Number(numeroMesa))
                .sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
        }

        function abrirResumoMesa(numeroMesa) {
            mesaContaAtual = Number(numeroMesa);
            const pedidosMesa = obterPedidosMesa(mesaContaAtual);
            const pedidosAtivos = pedidosMesa.filter(p => !['cancelado', 'fechado'].includes((p.status || '').toLowerCase()));
            const totalGeral = pedidosMesa
                .filter(p => (p.status || '').toLowerCase() !== 'cancelado')
                .reduce((sum, pedido) => sum + Number(pedido.total || 0), 0);
            const totalAberto = pedidosAtivos.reduce((sum, pedido) => sum + Number(pedido.total || 0), 0);

            document.getElementById('conta-mesa-titulo').textContent = `Conta da Mesa ${mesaContaAtual}`;
            document.getElementById('conta-mesa-resumo').innerHTML = `
                <div class="grid-2" style="gap:0.8rem;">
                    <div class="kpi" style="padding:1rem;"><div class="kpi-label">Pedidos da mesa</div><div class="kpi-value" style="font-size:1.35rem;">${pedidosMesa.length}</div></div>
                    <div class="kpi" style="padding:1rem;"><div class="kpi-label">Total acumulado</div><div class="kpi-value" style="font-size:1.35rem;">R$ ${totalGeral.toFixed(2).replace('.', ',')}</div></div>
                    <div class="kpi" style="padding:1rem;"><div class="kpi-label">Em aberto</div><div class="kpi-value" style="font-size:1.35rem;">R$ ${totalAberto.toFixed(2).replace('.', ',')}</div></div>
                    <div class="kpi" style="padding:1rem;"><div class="kpi-label">Pedidos ativos</div><div class="kpi-value" style="font-size:1.35rem;">${pedidosAtivos.length}</div></div>
                </div>
            `;

            const listaPedidos = document.getElementById('conta-mesa-pedidos');
            if (!pedidosMesa.length) {
                listaPedidos.innerHTML = `<div class="card" style="padding:1rem; color:#64748b;">Nenhum pedido registrado nesta mesa.</div>`;
            } else {
                listaPedidos.innerHTML = pedidosMesa.map(p => `
                    <div class="card" style="padding:0.9rem; border-left:4px solid #cbd5e1;">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.4rem;">
                            <strong style="color:#1e293b;">Pedido #${p.id}</strong>
                            <span class="badge badge-${p.status}">${String(p.status || '').toUpperCase()}</span>
                        </div>
                        <div style="font-size:0.78rem; color:#64748b; margin-bottom:0.35rem;">${new Date(p.created_at).toLocaleString('pt-BR')}</div>
                        <div style="font-size:0.86rem; color:#334155;">${p.itens.map(i => `${i.quantidade}x ${i.nome}`).join(' · ')}</div>
                        <div style="margin-top:0.45rem; font-weight:700; color:#1e293b;">R$ ${Number(p.total || 0).toFixed(2).replace('.', ',')}</div>
                    </div>
                `).join('');
            }

            const btnFecharConta = document.getElementById('btn-fechar-conta-mesa');
            btnFecharConta.disabled = pedidosAtivos.length === 0;
            btnFecharConta.style.opacity = pedidosAtivos.length === 0 ? '0.6' : '1';

            document.getElementById('modal-conta-mesa').classList.add('active');
        }

        function fecharModalContaMesa() {
            document.getElementById('modal-conta-mesa').classList.remove('active');
            mesaContaAtual = null;
        }

        async function fecharContaMesa() {
            if (!mesaContaAtual) return;
            if (!contexto.caixaAberto) {
                alert('Abra o caixa antes de fechar a conta da mesa.');
                return;
            }

            const pedidosMesa = obterPedidosMesa(mesaContaAtual);
            const pedidosParaFechar = pedidosMesa.filter(p => !['cancelado', 'fechado'].includes((p.status || '').toLowerCase()));

            if (!pedidosParaFechar.length) {
                alert('Não há pedidos abertos nesta mesa para fechar.');
                return;
            }

            const totalMesa = pedidosParaFechar.reduce((soma, pedido) => soma + Number(pedido.total || 0), 0);
            const formaPagamento = perguntarFormaPagamento(totalMesa, mesaContaAtual);
            if (!formaPagamento) return;

            if (!confirm(`Fechar conta da Mesa ${mesaContaAtual}? ${pedidosParaFechar.length} pedido(s) serão marcados como FECHADO em ${formaPagamento.toUpperCase()}.`)) {
                return;
            }

            for (const pedido of pedidosParaFechar) {
                await atualizarStatus(pedido.id, 'fechado', false, formaPagamento);
            }

            registrarVendaCaixa({
                mesa: mesaContaAtual,
                total: totalMesa,
                forma_pagamento: formaPagamento,
                pedido_ids: pedidosParaFechar.map(p => p.id)
            });

            await carregarPedidos();
            renderizarPedidos();
            renderizarMesas();
            atualizarKPIsPedidos();
            abrirResumoMesa(mesaContaAtual);
            atualizarPainelCaixa();
            alert(`Conta da Mesa ${mesaContaAtual} fechada com sucesso em ${formaPagamento.toUpperCase()}.`);
        }

        // CAIXA
        function moeda(valor) {
            return `R$ ${Number(valor || 0).toFixed(2).replace('.', ',')}`;
        }

        function estadoCaixaPadrao() {
            const hoje = new Date().toISOString().slice(0, 10);
            return {
                aberto: false,
                data_referencia: hoje,
                abertura: null,
                valor_inicial: 0,
                movimentos: []
            };
        }

        function carregarEstadoCaixa() {
            const salvo = JSON.parse(localStorage.getItem(storageKey('caixa')) || '{}');
            const padrao = estadoCaixaPadrao();
            const dataRef = salvo.data_referencia || padrao.data_referencia;
            const hoje = new Date().toISOString().slice(0, 10);
            const movimentos = dataRef === hoje ? (salvo.movimentos || []) : [];

            contexto.caixaAberto = !!salvo.aberto && dataRef === hoje;
            contexto.caixaAbertura = contexto.caixaAberto ? (salvo.abertura || null) : null;
            contexto.caixaValorInicial = contexto.caixaAberto ? Number(salvo.valor_inicial || 0) : 0;
            contexto.caixaMovimentos = movimentos;

            salvarEstadoCaixa();
        }

        function salvarEstadoCaixa() {
            localStorage.setItem(storageKey('caixa'), JSON.stringify({
                aberto: contexto.caixaAberto,
                data_referencia: new Date().toISOString().slice(0, 10),
                abertura: contexto.caixaAbertura,
                valor_inicial: Number(contexto.caixaValorInicial || 0),
                movimentos: contexto.caixaMovimentos || []
            }));
        }

        function resumoCaixa() {
            const base = { dinheiro: 0, cartao: 0, pix: 0, vendas: 0 };
            (contexto.caixaMovimentos || []).forEach(m => {
                const valor = Number(m.total || 0);
                base.vendas += valor;
                if (m.forma_pagamento && Object.prototype.hasOwnProperty.call(base, m.forma_pagamento)) {
                    base[m.forma_pagamento] += valor;
                }
            });
            return base;
        }

        function atualizarPainelCaixa() {
            const resumo = resumoCaixa();

            document.getElementById('caixa-status').textContent = contexto.caixaAberto ? 'Sim' : 'Não';
            document.getElementById('btn-abrir-caixa').style.display = contexto.caixaAberto ? 'none' : 'block';
            document.getElementById('btn-fechar-caixa').style.display = contexto.caixaAberto ? 'block' : 'none';
            document.getElementById('caixa-abertura').textContent = contexto.caixaAbertura
                ? new Date(contexto.caixaAbertura).toLocaleString('pt-BR')
                : '-';
            document.getElementById('caixa-valor-inicial').textContent = moeda(contexto.caixaValorInicial);
            document.getElementById('caixa-total-vendas').textContent = moeda(resumo.vendas);
            document.getElementById('caixa-total-dinheiro').textContent = moeda(resumo.dinheiro);
            document.getElementById('caixa-total-cartao').textContent = moeda(resumo.cartao);
            document.getElementById('caixa-total-pix').textContent = moeda(resumo.pix);

            const lista = document.getElementById('caixa-resumo-lista');
            if (!lista) return;
            if (!contexto.caixaMovimentos.length) {
                lista.innerHTML = '<div style="font-size:0.8rem;color:#64748b;">Nenhuma venda registrada no caixa hoje.</div>';
                return;
            }

            lista.innerHTML = [...contexto.caixaMovimentos]
                .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
                .slice(0, 12)
                .map(m => `
                    <div style="display:flex;justify-content:space-between;gap:0.6rem;font-size:0.8rem;color:#334155;border-bottom:1px dashed #e2e8f0;padding-bottom:0.32rem;">
                        <span>Mesa ${m.mesa} · ${String(m.forma_pagamento || '-').toUpperCase()} · ${new Date(m.created_at).toLocaleTimeString('pt-BR')}</span>
                        <strong>${moeda(m.total)}</strong>
                    </div>
                `).join('');
        }

        function normalizarFormaPagamento(valor) {
            const forma = String(valor || '').trim().toLowerCase();
            if (forma === 'dinheiro' || forma === 'cartao' || forma === 'pix') return forma;
            if (forma === 'cartão') return 'cartao';
            return null;
        }

        function perguntarFormaPagamento(totalMesa, mesa) {
            const resposta = prompt(`Forma de pagamento da Mesa ${mesa} (${moeda(totalMesa)}): dinheiro, cartao ou pix`, 'dinheiro');
            if (resposta === null) return null;
            const forma = normalizarFormaPagamento(resposta);
            if (!forma) {
                alert('Forma inválida. Use: dinheiro, cartao ou pix.');
                return null;
            }
            return forma;
        }

        function registrarVendaCaixa({ mesa, total, forma_pagamento, pedido_ids = [] }) {
            contexto.caixaMovimentos.push({
                mesa,
                total: Number(total || 0),
                forma_pagamento,
                pedido_ids,
                created_at: new Date().toISOString()
            });
            salvarEstadoCaixa();
        }

        function abrirCaixa() {
            if (contexto.caixaAberto) return;
            const entrada = prompt('Informe o valor inicial do caixa (ex: 100,00):', '0,00');
            if (entrada === null) return;
            const valorInicial = Number(String(entrada).replace(',', '.'));
            if (Number.isNaN(valorInicial) || valorInicial < 0) {
                alert('Valor inicial inválido.');
                return;
            }

            contexto.caixaAberto = true;
            contexto.caixaAbertura = new Date().toISOString();
            contexto.caixaValorInicial = valorInicial;
            const hoje = new Date().toISOString().slice(0, 10);
            const salvo = JSON.parse(localStorage.getItem(storageKey('caixa')) || '{}');
            if ((salvo.data_referencia || '') !== hoje) {
                contexto.caixaMovimentos = [];
            }
            salvarEstadoCaixa();
            atualizarPainelCaixa();
        }

        function fecharCaixa() {
            if (!contexto.caixaAberto) return;
            const resumo = resumoCaixa();
            const totalComInicial = Number(contexto.caixaValorInicial || 0) + resumo.vendas;
            if (!confirm(`Fechar caixa agora?\n\nVendas: ${moeda(resumo.vendas)}\nDinheiro: ${moeda(resumo.dinheiro)}\nCartão: ${moeda(resumo.cartao)}\nPix: ${moeda(resumo.pix)}\nTotal com inicial: ${moeda(totalComInicial)}`)) {
                return;
            }

            contexto.caixaAberto = false;
            contexto.caixaAbertura = null;
            contexto.caixaValorInicial = 0;
            salvarEstadoCaixa();
            atualizarPainelCaixa();
        }

        function obterPayloadConfiguracoes() {
            const nome = document.getElementById('config-nome').value;
            const cnpj = document.getElementById('config-cnpj').value;
            const mesas = parseInt(document.getElementById('config-mesas').value) || 10;
            const urlBasePublica = (document.getElementById('config-url-base').value || '').trim().replace(/\/$/, '');
            const capa = document.getElementById('capa-preview').dataset.base64 || '';
            const capaPosicao = document.getElementById('config-capa-posicao').value || 'center';
            const logo = document.getElementById('logo-preview').dataset.base64 || '';
            const horariosCategoria = coletarHorariosCategoriaFormulario();
            const temaCorPrimaria = document.getElementById('config-cor-primaria').value || '#3b82f6';
            const temaCorSecundaria = document.getElementById('config-cor-secundaria').value || '#10b981';
            const temaCorDestaque = document.getElementById('config-cor-destaque').value || '#1e293b';
            const estiloBotao = document.getElementById('config-estilo-botao').value || 'rounded';
            const deliveryAtivo = !!document.getElementById('config-delivery-ativo')?.checked;
            const deliveryEnderecoOrigem = (document.getElementById('config-delivery-origem')?.value || '').trim();
            const deliveryMapsKey = (document.getElementById('config-maps-key')?.value || '').trim();
            const deliveryWhatsappEntregador = (document.getElementById('config-whatsapp-entregador')?.value || '').replace(/\D/g, '');
            const whatsappApiAtivo = !!document.getElementById('config-whatsapp-api-ativo')?.checked;
            const whatsappPhoneNumberId = (document.getElementById('config-whatsapp-phone-id')?.value || '').replace(/\D/g, '');
            const whatsappAccessToken = (document.getElementById('config-whatsapp-access-token')?.value || '').trim();
            const whatsappVerifyToken = (document.getElementById('config-whatsapp-verify-token')?.value || '').trim();

            const payload = {
                nome_unidade: nome,
                cnpj,
                total_mesas: mesas,
                url_base_publica: urlBasePublica,
                categorias: contexto.categorias,
                categoria_horarios: horariosCategoria,
                capa_cardapio_base64: capa,
                capa_posicao: capaPosicao,
                logo_base64: logo,
                tema_cor_primaria: temaCorPrimaria,
                tema_cor_secundaria: temaCorSecundaria,
                tema_cor_destaque: temaCorDestaque,
                estilo_botao: estiloBotao,
                delivery_ativo: deliveryAtivo,
                delivery_endereco_origem: deliveryEnderecoOrigem,
                delivery_google_maps_api_key: deliveryMapsKey,
                delivery_whatsapp_entregador: deliveryWhatsappEntregador,
                whatsapp_api_ativo: whatsappApiAtivo,
                whatsapp_phone_number_id: whatsappPhoneNumberId,
                whatsapp_access_token: whatsappAccessToken,
                whatsapp_verify_token: whatsappVerifyToken
            };

            contexto.restaurante = {
                nome_unidade: nome,
                cnpj,
                total_mesas: mesas,
                url_base_publica: urlBasePublica,
                capa_cardapio: capa,
                capa_posicao: capaPosicao,
                logo,
                tema_cor_primaria: temaCorPrimaria,
                tema_cor_secundaria: temaCorSecundaria,
                tema_cor_destaque: temaCorDestaque,
                estilo_botao: estiloBotao,
                delivery_ativo: deliveryAtivo,
                delivery_endereco_origem: deliveryEnderecoOrigem,
                delivery_google_maps_api_key: deliveryMapsKey,
                delivery_whatsapp_entregador: deliveryWhatsappEntregador,
                whatsapp_api_ativo: whatsappApiAtivo,
                whatsapp_phone_number_id: whatsappPhoneNumberId,
                whatsapp_access_token: whatsappAccessToken,
                whatsapp_verify_token: whatsappVerifyToken
            };

            return { payload, horariosCategoria };
        }

        function salvarRascunhoConfiguracoes() {
            const { horariosCategoria } = obterPayloadConfiguracoes();
            const localAtual = JSON.parse(localStorage.getItem(storageKey('restaurante_config')) || '{}');
            localStorage.setItem(storageKey('restaurante_config'), JSON.stringify({
                ...contexto.restaurante,
                categorias: contexto.categorias,
                horarios_categoria: horariosCategoria,
                publicado_em: localAtual.publicado_em || null,
                rascunho_em: new Date().toISOString()
            }));
            contexto.modoApi = false;
            aplicarConfiguracaoNaTela();
            alert('Rascunho salvo no painel.');
        }

        async function publicarConfiguracoes() {
            const { payload, horariosCategoria } = obterPayloadConfiguracoes();
            const localAtual = JSON.parse(localStorage.getItem(storageKey('restaurante_config')) || '{}');
            const publicadoEm = new Date().toISOString();

            localStorage.setItem(storageKey('restaurante_config'), JSON.stringify({
                ...contexto.restaurante,
                categorias: contexto.categorias,
                horarios_categoria: horariosCategoria,
                publicado_em: publicadoEm,
                rascunho_em: localAtual.rascunho_em || null
            }));

            localStorage.setItem(`restaurante_publicado_${contexto.slug}`, JSON.stringify({
                ...contexto.restaurante,
                categorias: contexto.categorias,
                horarios_categoria: horariosCategoria,
                publicado_em: publicadoEm
            }));

            try {
                const res = await fetch(`${API_URL}/api/admin/restaurante/${contexto.slug}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'token-acesso': contexto.token
                    },
                    body: JSON.stringify(payload)
                });

                if (!res.ok) {
                    throw new Error('Falha ao salvar na API');
                }
                contexto.modoApi = true;
                alert('Alterações publicadas no cardápio!');
            } catch (e) {
                contexto.modoApi = false;
                console.warn('Configuração salva somente localmente:', e.message);
                alert('API indisponível. O rascunho foi salvo apenas no painel admin.');
            }

            contexto.mesas = [];
            await carregarMesas();
            aplicarConfiguracaoNaTela();
            renderizarMesas();
        }

        // RENDERIZAÇÃO GERAL
        function atualizarKPIsPedidos() {
            document.getElementById('pedidos-hoje').textContent = contexto.pedidos.length;
            const faturamento = contexto.pedidos
                .filter(p => (p.status || '').toLowerCase() !== 'cancelado')
                .reduce((sum, p) => sum + Number(p.total || 0), 0);
            document.getElementById('faturamento-hoje').textContent = `R$ ${faturamento.toFixed(2).replace('.', ',')}`;

            const pedidosAbertos = (contexto.pedidos || []).filter((p) => {
                const status = String(p.status || '').toLowerCase();
                return ['novo', 'preparando', 'pronto', 'em_entrega'].includes(status);
            });

            const pendentesDelivery = pedidosAbertos.filter((p) => String(p.tipo_entrega || '').toLowerCase() === 'delivery').length;
            const pendentesPedidos = pedidosAbertos.length - pendentesDelivery;

            const badgePedidos = document.getElementById('nav-pedidos-badge');
            if (badgePedidos) {
                badgePedidos.textContent = String(pendentesPedidos);
                badgePedidos.classList.toggle('hidden', pendentesPedidos <= 0);

                if (ultimoTotalPendentesNav !== null && pendentesPedidos > ultimoTotalPendentesNav) {
                    badgePedidos.classList.remove('pulse');
                    void badgePedidos.offsetWidth;
                    badgePedidos.classList.add('pulse');
                    clearTimeout(navBadgePulseTimer);
                    navBadgePulseTimer = setTimeout(() => badgePedidos.classList.remove('pulse'), 2600);
                }

                ultimoTotalPendentesNav = pendentesPedidos;
            }

            const badgeDelivery = document.getElementById('nav-delivery-badge');
            if (badgeDelivery) {
                badgeDelivery.textContent = String(pendentesDelivery);
                badgeDelivery.classList.toggle('hidden', pendentesDelivery <= 0);

                if (ultimoTotalPendentesDeliveryNav !== null && pendentesDelivery > ultimoTotalPendentesDeliveryNav) {
                    badgeDelivery.classList.remove('pulse');
                    void badgeDelivery.offsetWidth;
                    badgeDelivery.classList.add('pulse');
                    clearTimeout(navDeliveryBadgePulseTimer);
                    navDeliveryBadgePulseTimer = setTimeout(() => badgeDelivery.classList.remove('pulse'), 2600);
                }

                ultimoTotalPendentesDeliveryNav = pendentesDelivery;
            }
        }

        function renderizarTudo() {
            renderizarProdutos();
            renderizarPedidos();
            renderizarMesas();
            renderizarEntregadores();
            atualizarPainelCorridaTempoReal();
            renderizarEtapasCorrida(0);
            atualizarMapaCorrida(false);

            const autoSeguir = document.getElementById('corrida-auto-seguir');
            if (autoSeguir) autoSeguir.checked = !!contexto.corridaAutoSeguir;

            carregarEstadoCaixa();
            atualizarPainelCaixa();

            aplicarConfiguracaoNaTela();
            atualizarKPIsPedidos();
        }

        // INICIAR
        window.addEventListener('error', (event) => {
            mostrarFalhaInicializacao(`Erro em tempo de execução: ${event?.message || 'desconhecido'}`, event?.error || event);
        });

        window.addEventListener('unhandledrejection', (event) => {
            const mensagem = event?.reason?.message || String(event?.reason || 'promessa rejeitada');
            mostrarFalhaInicializacao(`Erro assíncrono: ${mensagem}`, event?.reason || event);
        });

        window.addEventListener('load', () => {
            inicializar();
        });
    