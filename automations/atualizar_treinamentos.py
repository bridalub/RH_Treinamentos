"""Automação Playwright que baixa a planilha 'DTB Bridalub - Por Usuário' do CSOD.

Reaproveita o fluxo de navegação validado manualmente (login, menu de
Relatórios/Painéis, atualizar painel, exportar widget). Diferente da versão
original, esta função NÃO decide qual aba usar — apenas baixa o .xlsx bruto
e devolve o caminho do arquivo; a escolha da aba oficial "(2)" e toda a
validação ficam em utils/excel_import.py, que é a única fonte de verdade
sobre qual aba é válida.

As credenciais nunca ficam gravadas em texto puro no código: são passadas
como parâmetros (a tela de Atualização pede login/senha do CSOD ao operador
no momento do clique, ou lê de variáveis de ambiente CSOD_CPF/CSOD_SENHA
quando executado via linha de comando).
"""
import os
import re
import subprocess
from datetime import datetime
from typing import Callable, Optional

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

URL_LOGIN = "https://grupocosan.csod.com/login/render.aspx?id=distribuidores"

# textos do modal de erro do CSOD quando CPF/senha estão incorretos — cobre a
# variação em português (padrão do site) e em inglês (quando o navegador
# traduz a página automaticamente, como no Google Translate)
_PADRAO_ERRO_LOGIN = re.compile(
    r"invalid authentication credentials|incorrect password|temporarily locked|"
    r"credenciais.*inv[aá]lidas|senha incorreta|usu[aá]rio ou senha inv[aá]lid|"
    r"temporariamente bloquead",
    re.I,
)


class AutomacaoError(Exception):
    """Erro genérico da automação (elemento não encontrado, timeout inesperado, etc.)."""


class LoginInvalidoError(AutomacaoError):
    """CPF e/ou senha recusados pelo CSOD — a operação deve ser cancelada e o
    usuário precisa informar credenciais corretas antes de tentar de novo."""


def _detectar_falha_login(page) -> Optional[str]:
    """Após o clique em 'Entrar', verifica se o CSOD exibiu o modal de
    credenciais inválidas. Retorna o texto do modal, ou None se o login
    seguiu normalmente (nenhum erro apareceu dentro do tempo de espera)."""
    try:
        modal_erro = page.get_by_text(_PADRAO_ERRO_LOGIN).first
        modal_erro.wait_for(state="visible", timeout=8_000)
        return modal_erro.inner_text()
    except PlaywrightTimeoutError:
        return None


def _lancar_navegador(p, headless: bool, avisar: Callable[[str], None]):
    """Usa exclusivamente o Chromium baixado pelo próprio Playwright — nunca
    depende de um navegador já instalado no sistema operacional (`channel=
    "chrome"`/`"msedge"` ou `executable_path` apontando pro Chrome real).
    Era exatamente essa dependência que quebrava a automação no container
    Linux do Streamlit Community Cloud (sem Chrome instalado), mesmo
    funcionando no Windows local (que tem Chrome, mas não precisa mais
    dele) — agora o comportamento é o mesmo nos dois ambientes: primeira
    execução baixa o binário do Chromium (uma única vez, fica em cache no
    ambiente onde roda), execuções seguintes só o reutilizam."""
    try:
        return p.chromium.launch(headless=headless, slow_mo=300 if not headless else 0)
    except Exception as erro:
        mensagem = str(erro).lower()
        if "executable doesn't exist" not in mensagem and "playwright install" not in mensagem:
            raise  # erro sem relação com navegador ausente — não esconde outras falhas
        avisar("Chromium do Playwright ainda não instalado neste ambiente — baixando agora (só na primeira vez)...")
        try:
            subprocess.run(["playwright", "install", "chromium"], check=True, capture_output=True, timeout=300)
        except Exception as erro_instalacao:
            raise AutomacaoError(
                "Não foi possível baixar o Chromium do Playwright para rodar a automação. "
                f"Detalhe: {erro_instalacao}"
            ) from erro_instalacao
        return p.chromium.launch(headless=headless, slow_mo=300 if not headless else 0)


def baixar_planilha_treinamentos(
    cpf: str,
    senha: str,
    pasta_destino: str,
    headless: bool = False,
    on_progress: Optional[Callable[[str], None]] = None,
) -> str:
    """Executa o fluxo completo no CSOD e retorna o caminho do .xlsx baixado.

    Se o login falhar (CPF/senha incorretos), levanta LoginInvalidoError e
    interrompe a automação imediatamente — nenhuma outra etapa é executada.
    Quando `on_progress` é informado, cada etapa relevante é reportada a ele
    (ex.: para exibir o andamento em tempo real na tela de Atualização)."""
    os.makedirs(pasta_destino, exist_ok=True)
    avisar = on_progress or (lambda _msg: None)

    with sync_playwright() as p:
        avisar("Abrindo o navegador e o portal do CSOD...")
        browser = _lancar_navegador(p, headless, avisar)
        page = browser.new_page()

        try:
            page.goto(URL_LOGIN, wait_until="domcontentloaded", timeout=60_000)

            avisar("Enviando CPF e senha...")
            page.get_by_role("textbox", name="CPF (apenas números)").fill(cpf)
            page.get_by_role("textbox", name="Senha").fill(senha)
            page.get_by_role("button", name="Entrar").click()

            mensagem_erro = _detectar_falha_login(page)
            if mensagem_erro:
                raise LoginInvalidoError(
                    "CPF ou senha incorretos — o CSOD recusou o login e a automação foi cancelada. "
                    "Corrija as credenciais nos campos acima e execute novamente. "
                    f"(mensagem do site: {mensagem_erro.strip()[:200]})"
                )
            avisar("Login realizado com sucesso.")
            page.wait_for_timeout(2_000)

            try:
                botao_concordo = page.get_by_role("button", name="Concordo")
                botao_concordo.wait_for(state="visible", timeout=5_000)
                botao_concordo.click()
                avisar("Termos aceitos.")
                page.wait_for_timeout(3_000)
            except PlaywrightTimeoutError:
                pass

            avisar("Abrindo o menu de navegação...")
            try:
                page.locator("div").filter(has_text="Mostrar Menu de Navegação").click(timeout=10_000)
            except PlaywrightTimeoutError:
                page.get_by_role("button", name="Mostrar Menu de Navegação").click(timeout=10_000)

            avisar("Acessando Relatórios > Painéis...")
            page.get_by_test_id("nav-item-Relat&#243;rios").click(timeout=10_000)
            page.get_by_test_id("nav-item-Pain&#233;is").click(timeout=30_000)

            avisar("Atualizando o painel — isso pode levar até 1 minuto...")
            page.get_by_role("button", name="Opções").click(timeout=50_000)
            page.get_by_role("link", name="Atualizar").click(timeout=30_000)
            page.wait_for_timeout(60_000)

            avisar("Abrindo o menu de exportação do widget...")
            seta_widget = page.locator('//*[@id="dashboardLayoutRoot"]/div[5]/span/div[1]/span[2]/span/a/span')
            item_exportar = page.locator('//*[@id="dashboardLayoutRoot"]/div[5]/span/div[1]/span[2]/span/ul/li[2]/a')

            for _tentativa in range(3):
                seta_widget.click(timeout=10_000)
                try:
                    item_exportar.wait_for(state="visible", timeout=5_000)
                    break
                except PlaywrightTimeoutError:
                    continue
            else:
                raise AutomacaoError("Não foi possível abrir o menu do widget para exportar.")

            avisar("Iniciando o download do relatório...")
            with page.context.expect_event("download", timeout=60_000) as download_info:
                item_exportar.click(timeout=10_000)
            download = download_info.value

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            caminho_final = os.path.join(pasta_destino, f"dtb_bridalub_por_usuario_{timestamp}.xlsx")
            download.save_as(caminho_final)
            avisar(f"Download concluído: {caminho_final}")
            return caminho_final
        finally:
            browser.close()


if __name__ == "__main__":
    cpf_env = os.environ.get("CSOD_CPF")
    senha_env = os.environ.get("CSOD_SENHA")
    if not cpf_env or not senha_env:
        raise SystemExit(
            "Defina as variáveis de ambiente CSOD_CPF e CSOD_SENHA antes de rodar este script "
            "(ex.: set CSOD_CPF=... && set CSOD_SENHA=... no PowerShell/CMD)."
        )
    destino = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "downloads")
    caminho = baixar_planilha_treinamentos(cpf_env, senha_env, destino, on_progress=print)
    print(f"Planilha baixada em: {caminho}")
