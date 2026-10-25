# QCY Desktop App

Controle local de cancelamento de ruído do **QCY H3 comum** pelo computador, sem precisar abrir o aplicativo QCY no celular durante o uso.

Interface gráfica e terminal permitem consultar ANC e selecionar **Normal**, **Barulho** ou **Adaptável**. Uma mudança só é apresentada como concluída depois de consultar novamente o fone e confirmar o estado aplicado.

Projeto independente, sem vínculo com a QCY. Esta versão é executada pelo Python. Instaladores nativos, integração com o menu de aplicativos e empacotamento desktop ficam para uma etapa futura.

## Funcionalidades

- Consulta do modo informado pelo próprio fone.
- Seleção de Normal, Barulho e Adaptável, com leitura de confirmação.
- Interface gráfica com configuração dos endereços, conexão, consulta e aplicação.
- Terminal para as mesmas operações.
- Preferência local e restauração opcional ao abrir conexão de controle.
- Tratamento de timeout, respostas fragmentadas e respostas inválidas.
- Recuperação limitada no Linux, com restauração do áudio quando uma pausa for necessária.
- Uso local, sem conta QCY, telemetria ou servidor do projeto.

Não oferece equalizador, firmware, reset, aplicativo móvel, descoberta automática genérica ou instalador `.deb`, AppImage ou `.exe` nesta etapa.

## Compatibilidade

Validado fisicamente em **QCY H3 comum, firmware V0.9.1.2**. Isso não comprova compatibilidade com H3 Lite, Pro, H3S, outros QCY ou outros firmwares.

- **Linux:** terminal e interface testados no fone real. Consulta, troca Normal/Adaptável, confirmação, gravação de preferência e fechamento da interface foram exercitados.
- **Windows 11:** transporte BLE implementado e testado por simulação. Conexão, pareamento e áudio ainda precisam de validação física nesse sistema.
- **macOS:** não implementado.

## Requisitos

- Python **3.11 ou superior**.
- Adaptador com Bluetooth Low Energy e Bluetooth ativado.
- H3 ligado, com carga e próximo do computador.
- Tkinter para interface gráfica.
- Endereços de **áudio** e **controle BLE** do seu próprio fone.

Linux também requer `bluetoothctl` e `gatttool`, do ecossistema BlueZ. O terminal Linux usa somente a biblioteca padrão do Python. Windows usa **Bleak 3.0.2**; não requer ferramentas Linux.

## Instalação e execução no Linux

### 1. Instale os requisitos

Em Ubuntu/Debian que disponibilizem essas ferramentas nos pacotes:

```sh
sudo apt update
sudo apt install git python3 python3-venv python3-tk bluez
```

Confira:

```sh
python3 --version
command -v bluetoothctl
command -v gatttool
python3 -m tkinter
```

O último comando abre uma janela de demonstração; feche-a para continuar. Tkinter só é necessário para interface gráfica.

**gatttool é legado.** Algumas distribuições/versões do BlueZ não o fornecem. Se `command -v gatttool` não retornar um caminho, o transporte Linux desta versão não está pronto nesse ambiente. Não há substituição automática implementada.

### 2. Clone e abra

```sh
git clone https://github.com/feapolina/qcy-desktop-app.git
cd qcy-desktop-app
python3 -m qcy_h3 gui
```

Execute os comandos na **raiz do repositório clonado**. `python3 -m qcy_h3`, sem ação, também abre a interface. O terminal Linux não precisa de pacotes Python adicionais.

### 3. Configure seu fone

Pareie H3 nas configurações Bluetooth do Linux para áudio. Se celular estiver mantendo controle conectado, feche o aplicativo QCY ou desligue temporariamente Bluetooth do celular.

Na primeira execução, os endereços ficam vazios. Preencha os endereços do seu equipamento e clique em **Conectar / Reconectar**. Não precisa deixar celular conectado por USB ou depuração habilitada para usar o programa.

## Instalação e execução no Windows

Suporte físico ainda experimental. Use Windows 11 com Bluetooth LE e Python 3.11+ incluindo Tcl/Tk. Instale Python e Git pelas distribuições oficiais; confira `py --version` no PowerShell.

```powershell
git clone https://github.com/feapolina/qcy-desktop-app.git
cd qcy-desktop-app
py -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-windows.txt
.\.venv\Scripts\python -m qcy_h3 gui
```

Usar diretamente o Python do ambiente dispensa ativação e mudança de política do PowerShell. Pareie H3 nas configurações Bluetooth, informe os endereços na interface e teste primeiro **Consultar**. Testes simulados não substituem validação física.

## Identificação dos endereços

Áudio e controle podem usar endereços diferentes. **Não suponha que o endereço de áudio também seja o BLE.** Nenhum endereço real é distribuído como padrão.

No Linux, encontre seu fone pareado e consulte o endereço:

```sh
bluetoothctl devices
bluetoothctl info AA:BB:CC:DD:EE:FF
```

`AA:BB:CC:DD:EE:FF` é fictício. Substitua todos os exemplos pelos endereços do seu equipamento.

Uma busca BLE pode mostrar `QCY H3-APP` ou um dispositivo sem nome:

```sh
bluetoothctl --timeout 20 scan le
```

Anúncios podem ser intermitentes. Na investigação, foi necessário identificar o endereço de controle na comunicação entre app oficial e o próprio fone e depois conectar diretamente.

Se identificou um candidato do seu H3, consulte os serviços sem alterar ANC:

```sh
gatttool -b AA:BB:CC:DD:EE:FF -t public --primary
```

O serviço esperado é `0000a002-0000-1000-8000-00805f9b34fb`. Esse serviço sozinho não identifica unicamente um equipamento; confirme que o endereço pertence ao seu fone.

Se não conseguir descobrir o endereço, não use o de outro usuário. Identificação por captura HCI é investigação separada; consulte a [documentação Bluetooth do Android](https://source.android.com/docs/core/connect/bluetooth/verifying_debugging). Não publique relatórios Android ou capturas completas, pois podem conter informações privadas.

No Windows também é necessário obter os endereços do próprio equipamento. Ainda não há assistente de descoberta nem método Windows validado fisicamente para identificá-los.

## Uso da interface

1. Informe **Endereço BLE de controle** e **Endereço Bluetooth de áudio**.
2. Clique em **Conectar / Reconectar**. Conexão só fica pronta após resposta ANC válida.
3. Clique em **Consultar** para atualizar estado.
4. Selecione modo e clique em **Aplicar**.
5. Aguarde **ANC confirmado**, resultado da leitura posterior.

Aplicação confirmada também salva modo como preferência local. Selecionar item sem clicar em Aplicar não altera fone nem preferência de modo.

**Restaurar modo preferido ao conectar** é desativado por padrão. Quando habilitado, aplica preferência uma vez ao abrir conexão de controle. Não reaplica em cada consulta nem desfaz mudanças manuais durante a mesma conexão.

Configure endereços válidos antes de salvar restauração. Alterações dos endereços passam a valer ao clicar em Conectar / Reconectar.

Fechar janela encerra controle. Não desliga fone, não envia reset e não aplica outro ANC. Não existe daemon, inicialização automática ou reconexão contínua.

## Uso pelo terminal

Configure pela interface ou informe endereços. Opções globais vêm antes da ação:

```sh
python3 -m qcy_h3 --ble-address AA:BB:CC:DD:EE:FF --audio-address 11:22:33:44:55:66 status
python3 -m qcy_h3 --ble-address AA:BB:CC:DD:EE:FF --audio-address 11:22:33:44:55:66 set adaptavel
```

`11:22:33:44:55:66` também é fictício. Sem endereços válidos, termina com erro antes de tentar Bluetooth.

Com preferências salvas:

```sh
python3 -m qcy_h3 status
python3 -m qcy_h3 set normal
python3 -m qcy_h3 set barulho
python3 -m qcy_h3 set adaptavel
python3 -m qcy_h3 --help
```

Outro arquivo de preferências:

```sh
python3 -m qcy_h3 --config ./meu-h3.json --ble-address AA:BB:CC:DD:EE:FF --audio-address 11:22:33:44:55:66 set adaptavel
```

No Windows, substitua `python3` por `.\.venv\Scripts\python`.

Sucesso retorna código `0`, falha operacional retorna `1`, argumento inválido retorna `2`. Se alteração ocorrer mas gravação local falhar, programa reporta erro de gravação; consulte novamente estado do fone.

**Restauração habilitada também afeta `status`:** consulta pode abrir conexão e reaplicar preferência antes de retornar estado.

## Preferências

- Linux: `$XDG_CONFIG_HOME/qcy-h3/settings.json` ou, sem essa variável, `~/.config/qcy-h3/settings.json`.
- Windows: `%APPDATA%\qcy-h3\settings.json`; sem essa variável, `.config/qcy-h3` na pasta pessoal.
- `--config` substitui caminho nessa execução.

JSON contém endereços, modo preferido e restauração. Gravação usa arquivo temporário e substituição atômica para preservar arquivo anterior se substituição falhar. Arquivo inválido gera erro e não é sobrescrito automaticamente.

Preferências pertencem à aplicação; não modificam persistência do firmware. Não publique seu JSON. Nomes usuais estão no `.gitignore`; arquivos pessoais com outros nomes também precisam ficar fora dos commits.

## Funcionamento e protocolo

ANC é processado pelo fone. Computador envia comandos e consulta resultado pelo controle Bluetooth, separado da conexão de áudio.

Este H3 usa **JieLi RCSP sobre BLE/GATT**:

- Serviço: `0000a002-0000-1000-8000-00805f9b34fb`.
- Escrita: `00000001-0000-1000-8000-00805f9b34fb`.
- Notificações: `00000002-0000-1000-8000-00805f9b34fb`.
- Comandos internos QCY encapsulados no opcode RCSP `0xFF`.

Consulta usa `FE 01 17`. Aplicação usa `17 03` e os três bytes do modo:

```text
Normal:    02 00 00
Barulho:   01 01 02
Adaptável: 01 05 00
```

Esses conteúdos não são pacotes completos. Controlador acrescenta enquadramento RCSP, comprimento, sequência e terminador. Confere status e sequência, aceita notificações fragmentadas e lê estado depois de aplicar. Modos desconhecidos não são convertidos silenciosamente nos três modos conhecidos.

Início de sequência varia por instância e depois incrementa. Essa decisão veio de ausência de resposta em sessões com início fixo repetido. É mitigação empírica, não garantia contra colisões ou timeout.

### Linux

gatttool abre conexão direta, descobre handles e inscreve notificações. Não assume handles fixos entre firmwares nem depende de encontrar anúncio em toda execução.

Tenta abrir e consultar sem interromper áudio. Se abertura ou primeira resposta falhar com áudio conectado, faz uma tentativa adicional: pausa áudio, aguarda liberação do rádio, abre controle, consulta e reconecta áudio em bloco de limpeza. Falha de restauração é informada para reconexão manual.

Pode haver pausa breve no som. Não apaga pareamentos nem reinicia adaptador.

### Windows

Bleak conecta usando APIs BLE do sistema, valida serviço/características e recebe notificações. Compartilha controlador e protocolo com Linux. Não executa ferramentas Linux nem oferece fallback Windows comprovado fisicamente.

## Como foi desenvolvido

Pesquisa inicial de utilitários QCY e projetos de engenharia reversa foi seguida de análise local do APK, comparação do comportamento do app e captura HCI no equipamento de teste.

Trocas controladas entre os modos permitiram associar ações a comandos. Depois os comandos foram reproduzidos no Linux e respostas foram verificadas antes de construir terminal e interface.

Implementação escrita a partir do comportamento observado. Não contém APK, código decompilado, firmware, dados de conta ou capturas privadas. Histórico público recebe somente cópia saneada do programa; investigação pessoal e especificações locais não foram importadas.

Referências:

- [REA](https://github.com/morluto/rea): referência metodológica inicial.
- [Quicky](https://github.com/hui1601/Quicky): documentação QCY como ponto de partida; não representa necessariamente o mesmo protocolo deste H3.
- [JADX](https://github.com/skylot/jadx): ferramenta usada na análise local do aplicativo.
- [Bleak](https://bleak.readthedocs.io/): biblioteca usada no transporte Windows.

## Código e desenvolvimento

```text
qcy_h3/
  core.py          RCSP, controlador e preferências.
  transports.py    GATT Linux e BLE Windows.
  gui.py           Interface Tkinter.
  __main__.py      Terminal e ponto de entrada.
tests/
  test_controller.py
  test_platforms.py
requirements-windows.txt
```

Interface e terminal usam o mesmo controlador. Bluetooth roda fora da thread gráfica; fila entrega resultados à janela.

Testes, na raiz do clone:

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q qcy_h3
```

Verificação de tipos em ambiente virtual:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install mypy==2.4.0
.venv/bin/python -m mypy qcy_h3 --check-untyped-defs
```

No Windows, ajuste caminho para `.\.venv\Scripts\python`.

Testes usam endereços fictícios e Bluetooth simulado. Cobrem consulta, aplicação, confirmação, fragmentação, erros, sequência, preferências e recuperação. Não exigem hardware, APK, conta ou relatório Android. Simulação Windows não comprova teste físico nesse sistema.

## Problemas comuns

- **Interface sem endereços:** esperado na primeira execução; configure seu próprio equipamento.
- **`No module named qcy_h3`:** execute na raiz do clone, usando Python correto.
- **Interface indisponível:** confira Tkinter e sessão gráfica. Terminal pode funcionar sem janela.
- **Timeout:** confira endereços, carga, distância e adaptador; libere controle mantido pelo celular. Use Conectar / Reconectar para nova sessão.
- **Erro mesmo após áudio voltar:** recuperação de áudio não significa confirmação do ANC; preserve mensagem de falha.
- **JSON inválido:** revise configuração local ou use outro arquivo com `--config`; não publique arquivo pessoal.
- **Ajuste perdido após desligar:** causa no firmware não foi isolada. Restauração reaplica preferência pelo programa, sem torná-la persistente no firmware.

## Privacidade e contribuições

Só programa, testes e documentação pública são versionados. `.gitignore` exclui nomes usuais de configurações, APKs, dumps, capturas, chaves e credenciais.

Ao abrir issue, informe modelo, firmware, sistema, Python e mensagem revisada. Remova MACs, números de série, caminhos pessoais, emails e tokens. Não anexe bugreport Android completo ou captura Bluetooth bruta em issue pública.

Melhorias de interface, reconexão e validação física no Windows são contribuições úteis. Empacotamento como aplicativo desktop Linux será tratado em etapa futura.
