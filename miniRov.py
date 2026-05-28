import pygame
import math
import random
import heapq
import time

pygame.init()

LARGURA, ALTURA = 1500, 760
FPS = 60

TANQUE = pygame.Rect(40, 70, 780, 590)

CELL = 10
COLS = TANQUE.width // CELL
ROWS = TANQUE.height // CELL

DESCONHECIDO = 0
LIVRE = 1
OCUPADO = 2
ROTA = 3

FUNDO = (14, 18, 26)
PAINEL = (27, 35, 48)
PAINEL_2 = (38, 48, 64)
AGUA = (218, 235, 245)
GRADE = (198, 213, 225)
PAREDE = (70, 80, 90)
BRANCO = (245, 245, 245)
CINZA = (165, 170, 180)
CINZA_ESCURO = (45, 52, 62)
PRETO = (15, 15, 15)

AZUL = (0, 130, 255)
AZUL_CLARO = (90, 195, 255)
VERDE = (0, 220, 120)
AMARELO = (245, 200, 45)
VERMELHO = (240, 70, 70)
ROXO = (170, 90, 255)
LARANJA = (255, 145, 40)

HUD_X = 850
HUD_W = LARGURA - HUD_X

tela = pygame.display.set_mode((LARGURA, ALTURA))
pygame.display.set_caption("MiniROV Mapper - Dijkstra vs A* com Métricas em Tempo Real")
clock = pygame.time.Clock()

fonte = pygame.font.SysFont("Arial", 17)
fonte_pequena = pygame.font.SysFont("Arial", 14)
fonte_titulo = pygame.font.SysFont("Arial", 24, bold=True)
fonte_grande = pygame.font.SysFont("Arial", 30, bold=True)

paredes = [
    pygame.Rect(40, 70, 780, 18),
    pygame.Rect(40, 642, 780, 18),
    pygame.Rect(40, 70, 18, 590),
    pygame.Rect(802, 70, 18, 590),

    pygame.Rect(170, 185, 240, 24),
    pygame.Rect(510, 150, 24, 190),
    pygame.Rect(165, 450, 280, 24),
    pygame.Rect(610, 395, 160, 24),
    pygame.Rect(660, 235, 24, 130),
    pygame.Rect(330, 300, 140, 22),
]

obstaculos_extra = []

rov_x, rov_y = 120, 140
rov_ang = 0
rov_raio = 16

MARGEM_SEGURANCA = 5
RAIO_PLANEJAMENTO = rov_raio + MARGEM_SEGURANCA
DISTANCIA_REPLANEJAR = 30
DISTANCIA_MINIMA_PARADA = 8
LOOKAHEAD_CELULAS = 4

vel_mov = 3.0
vel_rot = 3.0
vel_auto = 2.2
alcance_sensor = 220

mostrar_sensores = True
mostrar_ambiente_real = True
mostrar_ajuda = False
ruido_sensor = False
pausado = False
modo_mapa = 1

caminho = []
mapa = [[DESCONHECIDO for _ in range(COLS)] for _ in range(ROWS)]

algoritmo_atual = "A*"
ponto_inicio = None
ponto_destino = None
caminho_planejado = []

modo_autonomo = False
indice_rota = 0
status_rota = "Nenhuma rota calculada"
replanejamentos = 0

metricas = {
    "Dijkstra": None,
    "A*": None
}

metricas_tempo_real = {
    "ativo": False,
    "algoritmo": None,
    "tempo_inicio_execucao": 0,
    "tempo_execucao_s": 0,
    "tempo_busca_ms": 0,
    "custo_total": 0,
    "custo_atual": 0,
    "custo_restante": 0,
    "nos_expandidos": 0,
    "progresso": 0
}

botoes_hud = {}


def texto(msg, x, y, cor=BRANCO, titulo=False, pequena=False, grande=False):
    if grande:
        f = fonte_grande
    elif titulo:
        f = fonte_titulo
    elif pequena:
        f = fonte_pequena
    else:
        f = fonte

    img = f.render(str(msg), True, cor)
    tela.blit(img, (x, y))


def desenhar_botao(label, valor, x, y, w=260, ativo=True):
    cor_fundo = PAINEL_2 if ativo else CINZA_ESCURO
    cor_texto = BRANCO if ativo else CINZA

    pygame.draw.rect(tela, cor_fundo, (x, y, w, 30), border_radius=8)
    texto(label, x + 10, y + 7, cor_texto, pequena=True)

    if valor is not None:
        texto(valor, x + 155, y + 7, cor_texto, pequena=True)


def mundo_para_grid(x, y):
    gx = int((x - TANQUE.left) // CELL)
    gy = int((y - TANQUE.top) // CELL)

    if 0 <= gx < COLS and 0 <= gy < ROWS:
        return gx, gy

    return None


def grid_para_mundo(gx, gy):
    x = TANQUE.left + gx * CELL + CELL // 2
    y = TANQUE.top + gy * CELL + CELL // 2
    return x, y


def mouse_para_grid(pos):
    x, y = pos
    if not TANQUE.collidepoint(x, y):
        return None
    return mundo_para_grid(x, y)


def marcar_grid(x, y, estado):
    pos = mundo_para_grid(x, y)

    if pos:
        gx, gy = pos

        if estado == OCUPADO:
            mapa[gy][gx] = OCUPADO
        elif mapa[gy][gx] != OCUPADO:
            mapa[gy][gx] = estado


def todos_obstaculos():
    return paredes + obstaculos_extra


def celula_bloqueada(gx, gy):
    rect = pygame.Rect(
        TANQUE.left + gx * CELL,
        TANQUE.top + gy * CELL,
        CELL,
        CELL
    )

    rect_seguro = rect.inflate(RAIO_PLANEJAMENTO * 2, RAIO_PLANEJAMENTO * 2)

    for p in todos_obstaculos():
        if rect_seguro.colliderect(p):
            return True

    return False


def colisao(x, y):
    caixa = pygame.Rect(
        x - RAIO_PLANEJAMENTO,
        y - RAIO_PLANEJAMENTO,
        RAIO_PLANEJAMENTO * 2,
        RAIO_PLANEJAMENTO * 2
    )

    for p in todos_obstaculos():
        if caixa.colliderect(p):
            return True

    return False


def adicionar_obstaculo_grid(gx, gy):
    cx, cy = grid_para_mundo(gx, gy)
    tamanho = 36

    novo = pygame.Rect(
        cx - tamanho // 2,
        cy - tamanho // 2,
        tamanho,
        tamanho
    )

    caixa_rov = pygame.Rect(rov_x - 25, rov_y - 25, 50, 50)

    if novo.colliderect(caixa_rov):
        return

    obstaculos_extra.append(novo)


def medir_sensor(x, y, angulo):
    pontos_livres = []

    for d in range(0, int(alcance_sensor), 4):
        ruido = 0

        if ruido_sensor:
            ruido = random.uniform(-1.8, 1.8)

        px = x + math.cos(math.radians(angulo + ruido)) * d
        py = y + math.sin(math.radians(angulo + ruido)) * d

        pontos_livres.append((px, py))
        ponto = pygame.Rect(px, py, 2, 2)

        for p in todos_obstaculos():
            if ponto.colliderect(p):
                distancia = d

                if ruido_sensor:
                    distancia += random.randint(-8, 8)
                    distancia = max(0, min(distancia, alcance_sensor))

                return distancia, (px, py), pontos_livres, True

    px = x + math.cos(math.radians(angulo)) * alcance_sensor
    py = y + math.sin(math.radians(angulo)) * alcance_sensor

    return alcance_sensor, (px, py), pontos_livres, False


def atualizar_mapeamento():
    marcar_grid(rov_x, rov_y, ROTA)

    angulos = [
        rov_ang - 90,
        rov_ang - 65,
        rov_ang - 40,
        rov_ang - 20,
        rov_ang,
        rov_ang + 20,
        rov_ang + 40,
        rov_ang + 65,
        rov_ang + 90,
        rov_ang + 180,
    ]

    leituras = {}

    for ang in angulos:
        dist, impacto, livres, bateu = medir_sensor(rov_x, rov_y, ang)

        for px, py in livres:
            marcar_grid(px, py, LIVRE)

        if bateu:
            marcar_grid(impacto[0], impacto[1], OCUPADO)

        leituras[int(ang % 360)] = dist

    return leituras


def distancia_frontal():
    dist, _, _, _ = medir_sensor(rov_x, rov_y, rov_ang)
    return dist


def porcentagem_mapeada():
    total = ROWS * COLS
    conhecidos = 0

    for linha in mapa:
        for cel in linha:
            if cel != DESCONHECIDO:
                conhecidos += 1

    return conhecidos / total * 100


def contar_obstaculos_detectados():
    total = 0

    for linha in mapa:
        for cel in linha:
            if cel == OCUPADO:
                total += 1

    return total


def cor_sensor(dist):
    if dist < 45:
        return VERMELHO
    elif dist < 90:
        return AMARELO
    return VERDE


def status_geral(leituras):
    menor = min(leituras.values()) if leituras else alcance_sensor

    if menor < 45:
        return "RISCO DE COLISÃO", VERMELHO
    elif menor < 90:
        return "PROXIMIDADE ALTA", AMARELO
    return "NAVEGAÇÃO SEGURA", VERDE


def vizinhos(gx, gy):
    movimentos = [
        (1, 0),
        (-1, 0),
        (0, 1),
        (0, -1)
    ]

    lista = []

    for dx, dy in movimentos:
        nx, ny = gx + dx, gy + dy

        if 0 <= nx < COLS and 0 <= ny < ROWS:
            if not celula_bloqueada(nx, ny):
                lista.append((nx, ny))

    return lista


def heuristica(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def reconstruir_caminho(veio_de, atual):
    caminho_final = [atual]

    while atual in veio_de:
        atual = veio_de[atual]
        caminho_final.append(atual)

    caminho_final.reverse()
    return caminho_final


def buscar_caminho(inicio, destino, algoritmo):
    tempo_inicio = time.perf_counter()

    fila = []
    heapq.heappush(fila, (0, inicio))

    veio_de = {}
    custo = {inicio: 0}
    visitados = set()

    while fila:
        _, atual = heapq.heappop(fila)

        if atual in visitados:
            continue

        visitados.add(atual)

        if atual == destino:
            tempo_fim = time.perf_counter()
            caminho_resultado = reconstruir_caminho(veio_de, atual)

            return {
                "caminho": caminho_resultado,
                "tempo_ms": (tempo_fim - tempo_inicio) * 1000,
                "nos": len(visitados),
                "custo": custo[atual],
                "encontrou": True
            }

        for prox in vizinhos(*atual):
            novo_custo = custo[atual] + 1

            if prox not in custo or novo_custo < custo[prox]:
                custo[prox] = novo_custo

                if algoritmo == "A*":
                    prioridade = novo_custo + heuristica(prox, destino)
                else:
                    prioridade = novo_custo

                heapq.heappush(fila, (prioridade, prox))
                veio_de[prox] = atual

    tempo_fim = time.perf_counter()

    return {
        "caminho": [],
        "tempo_ms": (tempo_fim - tempo_inicio) * 1000,
        "nos": len(visitados),
        "custo": 0,
        "encontrou": False
    }


def atualizar_metricas_tempo_real():
    global metricas_tempo_real

    if not metricas_tempo_real["ativo"]:
        return

    if not caminho_planejado:
        return

    tempo_atual = time.perf_counter()
    metricas_tempo_real["tempo_execucao_s"] = (
        tempo_atual - metricas_tempo_real["tempo_inicio_execucao"]
    )

    custo_total = max(len(caminho_planejado) - 1, 0)
    custo_atual = min(indice_rota, custo_total)
    custo_restante = max(custo_total - custo_atual, 0)

    metricas_tempo_real["custo_total"] = custo_total
    metricas_tempo_real["custo_atual"] = custo_atual
    metricas_tempo_real["custo_restante"] = custo_restante

    if custo_total > 0:
        metricas_tempo_real["progresso"] = int((custo_atual / custo_total) * 100)
    else:
        metricas_tempo_real["progresso"] = 0


def calcular_rota_atual(iniciar_auto=False):
    global caminho_planejado, modo_autonomo, indice_rota
    global status_rota, metricas, metricas_tempo_real

    if ponto_inicio is None or ponto_destino is None:
        caminho_planejado = []
        modo_autonomo = False
        status_rota = "Defina início e destino"
        metricas_tempo_real["ativo"] = False
        return

    if celula_bloqueada(*ponto_inicio) or celula_bloqueada(*ponto_destino):
        caminho_planejado = []
        modo_autonomo = False
        status_rota = "Início ou destino bloqueado"
        metricas_tempo_real["ativo"] = False
        return

    resultado = buscar_caminho(ponto_inicio, ponto_destino, algoritmo_atual)
    metricas[algoritmo_atual] = resultado

    caminho_planejado = resultado["caminho"]

    if not resultado["encontrou"]:
        modo_autonomo = False
        status_rota = f"{algoritmo_atual}: sem caminho"
        metricas_tempo_real["ativo"] = False
        return

    status_rota = f"{algoritmo_atual}: rota calculada"

    if iniciar_auto and len(caminho_planejado) > 1:
        modo_autonomo = True
        indice_rota = 0
        status_rota = f"{algoritmo_atual}: navegando"

        custo_total = max(len(caminho_planejado) - 1, 0)

        metricas_tempo_real = {
            "ativo": True,
            "algoritmo": algoritmo_atual,
            "tempo_inicio_execucao": time.perf_counter(),
            "tempo_execucao_s": 0,
            "tempo_busca_ms": resultado["tempo_ms"],
            "custo_total": custo_total,
            "custo_atual": 0,
            "custo_restante": custo_total,
            "nos_expandidos": resultado["nos"],
            "progresso": 0
        }


def encontrar_celula_livre_mais_proxima(gx, gy, limite=20):
    if 0 <= gx < COLS and 0 <= gy < ROWS and not celula_bloqueada(gx, gy):
        return gx, gy

    for raio in range(1, limite + 1):
        for dx in range(-raio, raio + 1):
            for dy in range(-raio, raio + 1):
                nx = gx + dx
                ny = gy + dy

                if 0 <= nx < COLS and 0 <= ny < ROWS:
                    if not celula_bloqueada(nx, ny):
                        return nx, ny

    return None


def caminho_bloqueado_a_frente():
    if not caminho_planejado:
        return True

    fim = min(indice_rota + LOOKAHEAD_CELULAS, len(caminho_planejado))

    for i in range(indice_rota, fim):
        gx, gy = caminho_planejado[i]

        if celula_bloqueada(gx, gy):
            return True

    return False


def obstaculo_frontal_perigoso():
    dist = distancia_frontal()
    return dist < DISTANCIA_REPLANEJAR


def colisao_iminente():
    dist = distancia_frontal()
    return dist < DISTANCIA_MINIMA_PARADA


def replanejar_por_obstaculo():
    global ponto_inicio, replanejamentos, status_rota
    global modo_autonomo, indice_rota, caminho_planejado

    if ponto_destino is None:
        modo_autonomo = False
        return

    atual = mundo_para_grid(rov_x, rov_y)

    if atual is None:
        modo_autonomo = False
        status_rota = "Fora do mapa"
        return

    celula_segura = encontrar_celula_livre_mais_proxima(*atual)

    if celula_segura is None:
        modo_autonomo = False
        status_rota = "Sem célula segura para replanejar"
        return

    ponto_inicio = celula_segura
    replanejamentos += 1
    indice_rota = 0
    status_rota = "Obstáculo detectado: replanejando"

    calcular_rota_atual(iniciar_auto=True)

    if not caminho_planejado:
        modo_autonomo = False
        status_rota = "Sem rota alternativa"


def mover_robo_autonomo():
    global rov_x, rov_y, rov_ang
    global modo_autonomo, indice_rota, status_rota
    global metricas_tempo_real

    if not modo_autonomo or len(caminho_planejado) < 2:
        modo_autonomo = False
        return

    if colisao_iminente():
        modo_autonomo = False
        status_rota = "Colisão iminente: navegação parada"
        metricas_tempo_real["ativo"] = False
        return

    if obstaculo_frontal_perigoso() or caminho_bloqueado_a_frente():
        replanejar_por_obstaculo()
        atualizar_metricas_tempo_real()
        return

    if indice_rota >= len(caminho_planejado):
        modo_autonomo = False
        status_rota = "Destino alcançado"
        atualizar_metricas_tempo_real()
        metricas_tempo_real["ativo"] = False
        return

    alvo_grid = caminho_planejado[indice_rota]

    if celula_bloqueada(*alvo_grid):
        replanejar_por_obstaculo()
        atualizar_metricas_tempo_real()
        return

    alvo_x, alvo_y = grid_para_mundo(*alvo_grid)

    dx = alvo_x - rov_x
    dy = alvo_y - rov_y
    distancia = math.hypot(dx, dy)

    if distancia < 4:
        indice_rota += 1
        atualizar_metricas_tempo_real()

        if indice_rota >= len(caminho_planejado):
            modo_autonomo = False
            status_rota = "Destino alcançado"
            metricas_tempo_real["ativo"] = False

        return

    rov_ang = math.degrees(math.atan2(dy, dx))

    passo = min(vel_auto, distancia)

    novo_x = rov_x + (dx / distancia) * passo
    novo_y = rov_y + (dy / distancia) * passo

    if colisao(novo_x, novo_y):
        replanejar_por_obstaculo()
        atualizar_metricas_tempo_real()
        return

    rov_x = novo_x
    rov_y = novo_y

    atualizar_metricas_tempo_real()


def desenhar_grade():
    for x in range(TANQUE.left, TANQUE.right, 40):
        pygame.draw.line(tela, GRADE, (x, TANQUE.top), (x, TANQUE.bottom), 1)

    for y in range(TANQUE.top, TANQUE.bottom, 40):
        pygame.draw.line(tela, GRADE, (TANQUE.left, y), (TANQUE.right, y), 1)


def desenhar_tanque_real():
    pygame.draw.rect(tela, AGUA, TANQUE)
    desenhar_grade()

    for p in paredes:
        pygame.draw.rect(tela, PAREDE, p, border_radius=4)

    for p in obstaculos_extra:
        pygame.draw.rect(tela, (120, 60, 55), p, border_radius=5)


def desenhar_mapa_construido():
    for gy in range(ROWS):
        for gx in range(COLS):
            estado = mapa[gy][gx]

            x = TANQUE.left + gx * CELL
            y = TANQUE.top + gy * CELL

            if estado == DESCONHECIDO:
                cor = (32, 38, 48)
            elif estado == LIVRE:
                cor = (150, 220, 238)
            elif estado == OCUPADO:
                cor = VERMELHO
            elif estado == ROTA:
                cor = ROXO
            else:
                cor = PRETO

            pygame.draw.rect(tela, cor, (x, y, CELL - 1, CELL - 1))


def desenhar_caminho():
    if len(caminho) > 2:
        pygame.draw.lines(tela, ROXO, False, caminho, 2)


def desenhar_sensores():
    if not mostrar_sensores:
        return

    angulos = [
        rov_ang - 90,
        rov_ang - 65,
        rov_ang - 40,
        rov_ang - 20,
        rov_ang,
        rov_ang + 20,
        rov_ang + 40,
        rov_ang + 65,
        rov_ang + 90,
        rov_ang + 180,
    ]

    for ang in angulos:
        dist, ponto, _, _ = medir_sensor(rov_x, rov_y, ang)
        cor = cor_sensor(dist)

        pygame.draw.line(tela, cor, (rov_x, rov_y), ponto, 2)
        pygame.draw.circle(tela, cor, (int(ponto[0]), int(ponto[1])), 4)


def desenhar_rov():
    pygame.draw.circle(tela, AZUL, (int(rov_x), int(rov_y)), rov_raio)
    pygame.draw.circle(tela, AZUL_CLARO, (int(rov_x), int(rov_y)), 7)

    frente_x = rov_x + math.cos(math.radians(rov_ang)) * 30
    frente_y = rov_y + math.sin(math.radians(rov_ang)) * 30

    pygame.draw.line(tela, BRANCO, (rov_x, rov_y), (frente_x, frente_y), 4)
    pygame.draw.circle(tela, BRANCO, (int(frente_x), int(frente_y)), 4)


def desenhar_pontos_rota():
    if ponto_inicio:
        x, y = grid_para_mundo(*ponto_inicio)
        pygame.draw.circle(tela, VERDE, (x, y), 8)
        texto("INÍCIO", x + 10, y - 10, VERDE, pequena=True)

    if ponto_destino:
        x, y = grid_para_mundo(*ponto_destino)
        pygame.draw.circle(tela, VERMELHO, (x, y), 8)
        texto("DESTINO", x + 10, y - 10, VERMELHO, pequena=True)


def desenhar_caminho_planejado():
    if len(caminho_planejado) < 2:
        return

    pontos = [grid_para_mundo(gx, gy) for gx, gy in caminho_planejado]
    cor = LARANJA if algoritmo_atual == "Dijkstra" else VERDE
    pygame.draw.lines(tela, cor, False, pontos, 4)


def desenhar_barra(nome, valor, maximo, x, y, cor, w=260):
    altura = 12
    proporcao = max(0, min(valor / maximo, 1))

    texto(nome, x, y, BRANCO, pequena=True)
    pygame.draw.rect(tela, CINZA_ESCURO, (x, y + 18, w, altura), border_radius=6)
    pygame.draw.rect(tela, cor, (x, y + 18, int(w * proporcao), altura), border_radius=6)


def desenhar_minimapa():
    mini_x = 1165
    mini_y = 95
    escala = 2

    texto("MINIMAPA", mini_x, mini_y - 28, AZUL_CLARO)

    pygame.draw.rect(
        tela,
        (18, 22, 30),
        (mini_x - 8, mini_y - 8, COLS * escala + 16, ROWS * escala + 16),
        border_radius=8
    )

    for gy in range(ROWS):
        for gx in range(COLS):
            estado = mapa[gy][gx]

            if estado == DESCONHECIDO:
                cor = (18, 22, 30)
            elif estado == LIVRE:
                cor = (115, 210, 235)
            elif estado == OCUPADO:
                cor = VERMELHO
            elif estado == ROTA:
                cor = ROXO
            else:
                cor = PRETO

            pygame.draw.rect(
                tela,
                cor,
                (mini_x + gx * escala, mini_y + gy * escala, escala, escala)
            )

    pos = mundo_para_grid(rov_x, rov_y)

    if pos:
        gx, gy = pos
        pygame.draw.circle(
            tela,
            AZUL,
            (mini_x + gx * escala, mini_y + gy * escala),
            4
        )


def desenhar_legenda(x, y):
    texto("LEGENDA", x, y, AZUL_CLARO)

    itens = [
        ("Desconhecido", (32, 38, 48)),
        ("Área livre", (150, 220, 238)),
        ("Obstáculo", VERMELHO),
        ("Rota ROV", ROXO),
        ("Rota planejada", VERDE if algoritmo_atual == "A*" else LARANJA),
        ("Obstáculo extra", (120, 60, 55)),
    ]

    yy = y + 28

    for nome, cor in itens:
        pygame.draw.rect(tela, cor, (x, yy, 14, 14), border_radius=3)
        texto(nome, x + 22, yy - 2, BRANCO, pequena=True)
        yy += 22


def desenhar_metricas_algoritmo(nome, x, y):
    dados = metricas[nome]
    ativo = nome == algoritmo_atual
    cor = VERDE if ativo else CINZA

    if dados is None:
        texto(f"{nome}: não testado", x, y, CINZA, pequena=True)
        return y + 22

    if not dados["encontrou"]:
        texto(f"{nome}: sem caminho", x, y, VERMELHO, pequena=True)
        texto(f"nós expandidos: {dados['nos']}", x, y + 18, VERMELHO, pequena=True)
        return y + 42

    texto(f"{nome}: testado", x, y, cor, pequena=True)
    texto(f"tempo: {dados['tempo_ms']:.3f} ms", x, y + 18, cor, pequena=True)
    texto(f"custo: {dados['custo']} | nós: {dados['nos']}", x, y + 36, cor, pequena=True)
    return y + 62


def desenhar_botao_interativo(nome, chave, x, y, w, h, ativo=False):
    global botoes_hud

    botoes_hud[chave] = pygame.Rect(x, y, w, h)

    if ativo:
        cor_fundo = VERDE
        cor_texto = PRETO
    else:
        cor_fundo = PAINEL_2
        cor_texto = BRANCO

    pygame.draw.rect(tela, cor_fundo, (x, y, w, h), border_radius=8)
    pygame.draw.rect(tela, AZUL_CLARO, (x, y, w, h), 1, border_radius=8)

    img = fonte_pequena.render(str(nome), True, cor_texto)
    texto_x = x + (w - img.get_width()) // 2
    texto_y = y + (h - img.get_height()) // 2

    tela.blit(img, (texto_x, texto_y))


def desenhar_botao_ajuste(nome, valor, chave_menos, chave_mais, x, y, w=250):
    global botoes_hud

    pygame.draw.rect(tela, PAINEL_2, (x, y, w, 28), border_radius=7)

    texto(nome, x + 10, y + 7, BRANCO, pequena=True)
    texto(str(valor), x + 140, y + 7, AZUL_CLARO, pequena=True)

    btn_menos = pygame.Rect(x + w - 58, y + 5, 22, 18)
    btn_mais = pygame.Rect(x + w - 30, y + 5, 22, 18)

    botoes_hud[chave_menos] = btn_menos
    botoes_hud[chave_mais] = btn_mais

    pygame.draw.rect(tela, CINZA_ESCURO, btn_menos, border_radius=4)
    pygame.draw.rect(tela, CINZA_ESCURO, btn_mais, border_radius=4)

    texto("-", btn_menos.x + 7, btn_menos.y + 1, BRANCO, pequena=True)
    texto("+", btn_mais.x + 5, btn_mais.y + 1, BRANCO, pequena=True)


def processar_clique_hud(pos):
    global algoritmo_atual, status_rota, modo_autonomo
    global ponto_inicio
    global vel_mov, vel_auto, alcance_sensor
    global mostrar_sensores, mostrar_ambiente_real, ruido_sensor
    global modo_mapa

    for chave, rect in botoes_hud.items():
        if rect.collidepoint(pos):

            if chave == "btn_dijkstra":
                algoritmo_atual = "Dijkstra"
                status_rota = "Dijkstra selecionado. Clique em INICIAR."
                modo_autonomo = False
                return True

            elif chave == "btn_astar":
                algoritmo_atual = "A*"
                status_rota = "A* selecionado. Clique em INICIAR."
                modo_autonomo = False
                return True

            elif chave == "btn_iniciar":
                if ponto_destino is not None:
                    ponto_inicio = mundo_para_grid(rov_x, rov_y)
                    calcular_rota_atual(iniciar_auto=True)
                else:
                    status_rota = "Escolha um destino primeiro."
                return True

            elif chave == "btn_parar":
                modo_autonomo = False
                status_rota = "Navegação autônoma parada."
                return True

            elif chave == "btn_limpar":
                obstaculos_extra.clear()
                status_rota = "Obstáculos extras removidos."
                return True

            elif chave == "vel_mov_menos":
                vel_mov = max(1.0, vel_mov - 0.5)
                status_rota = f"Velocidade manual: {vel_mov:.1f}"
                return True

            elif chave == "vel_mov_mais":
                vel_mov = min(8.0, vel_mov + 0.5)
                status_rota = f"Velocidade manual: {vel_mov:.1f}"
                return True

            elif chave == "vel_auto_menos":
                vel_auto = max(0.5, vel_auto - 0.2)
                status_rota = f"Velocidade autônoma: {vel_auto:.1f}"
                return True

            elif chave == "vel_auto_mais":
                vel_auto = min(6.0, vel_auto + 0.2)
                status_rota = f"Velocidade autônoma: {vel_auto:.1f}"
                return True

            elif chave == "alcance_menos":
                alcance_sensor = max(80, alcance_sensor - 20)
                status_rota = f"Alcance do sensor: {int(alcance_sensor)} px"
                return True

            elif chave == "alcance_mais":
                alcance_sensor = min(350, alcance_sensor + 20)
                status_rota = f"Alcance do sensor: {int(alcance_sensor)} px"
                return True

            elif chave == "toggle_sensores":
                mostrar_sensores = not mostrar_sensores
                status_rota = f"Sensores: {'ON' if mostrar_sensores else 'OFF'}"
                return True

            elif chave == "toggle_ambiente":
                mostrar_ambiente_real = not mostrar_ambiente_real
                status_rota = f"Ambiente real: {'ON' if mostrar_ambiente_real else 'OFF'}"
                return True

            elif chave == "toggle_ruido":
                ruido_sensor = not ruido_sensor
                status_rota = f"Ruído: {'ON' if ruido_sensor else 'OFF'}"
                return True

            elif chave == "toggle_mapa":
                modo_mapa += 1
                if modo_mapa > 3:
                    modo_mapa = 1
                status_rota = f"Modo mapa: {modo_mapa}"
                return True

    return False


def desenhar_comparativo(x, y):
    texto("PLANEJAMENTO DE ROTA", x, y, AZUL_CLARO)

    texto("Escolha o algoritmo:", x, y + 24, BRANCO, pequena=True)

    desenhar_botao_interativo(
        "Dijkstra",
        "btn_dijkstra",
        x,
        y + 48,
        120,
        32,
        algoritmo_atual == "Dijkstra"
    )

    desenhar_botao_interativo(
        "A*",
        "btn_astar",
        x + 130,
        y + 48,
        120,
        32,
        algoritmo_atual == "A*"
    )

    texto(
        "Modo: AUTÔNOMO" if modo_autonomo else "Modo: MANUAL",
        x,
        y + 92,
        VERDE if modo_autonomo else CINZA,
        pequena=True
    )

    texto(
        f"Status: {status_rota}",
        x,
        y + 112,
        AMARELO if modo_autonomo else CINZA,
        pequena=True
    )

    texto(f"Replanejamentos: {replanejamentos}", x, y + 132, BRANCO, pequena=True)

    desenhar_botao_interativo(
        "INICIAR ROTA",
        "btn_iniciar",
        x,
        y + 160,
        250,
        32,
        False
    )

    desenhar_botao_interativo(
        "PARAR",
        "btn_parar",
        x,
        y + 202,
        120,
        30,
        False
    )

    desenhar_botao_interativo(
        "LIMPAR OBS.",
        "btn_limpar",
        x + 130,
        y + 202,
        120,
        30,
        False
    )


def desenhar_hud(leituras):
    global botoes_hud

    botoes_hud = {}

    pygame.draw.rect(tela, PAINEL, (HUD_X, 0, HUD_W, ALTURA))

    status, cor_status = status_geral(leituras)

    col1_x = 880
    col2_x = 1165

    texto("MiniROV HUD", col1_x, 10, BRANCO, titulo=True)
    texto(status, col1_x, 38, cor_status)

    # -------------------------
    # Localização
    # -------------------------
    texto("LOCALIZAÇÃO", col1_x, 62, AZUL_CLARO)
    texto(f"X: {int(rov_x)} px", col1_x, 82, pequena=True)
    texto(f"Y: {int(rov_y)} px", col1_x, 99, pequena=True)
    texto(f"Ângulo: {int(rov_ang % 360)}°", col1_x, 116, pequena=True)

    # -------------------------
    # Mapeamento
    # -------------------------
    texto("MAPEAMENTO", col1_x, 140, AZUL_CLARO)
    desenhar_barra("Área mapeada", porcentagem_mapeada(), 100, col1_x, 160, VERDE, w=250)
    texto(f"Obstáculos detectados: {contar_obstaculos_detectados()}", col1_x, 194, pequena=True)
    texto(f"Modo mapa: {modo_mapa}", col1_x, 211, pequena=True)

    # -------------------------
    # Métricas em tempo real
    # -------------------------
    texto("MÉTRICAS EM TEMPO REAL", col1_x, 238, AZUL_CLARO)

    if metricas_tempo_real["algoritmo"] is not None:
        cor_alg = VERDE if metricas_tempo_real["algoritmo"] == "A*" else LARANJA

        texto(f"Algoritmo: {metricas_tempo_real['algoritmo']}", col1_x, 258, cor_alg, pequena=True)
        texto(f"Tempo busca: {metricas_tempo_real['tempo_busca_ms']:.3f} ms", col1_x, 275, BRANCO, pequena=True)
        texto(f"Tempo mov.: {metricas_tempo_real['tempo_execucao_s']:.2f} s", col1_x, 292, BRANCO, pequena=True)
        texto(
            f"Custo: {metricas_tempo_real['custo_atual']} / {metricas_tempo_real['custo_total']}",
            col1_x,
            309,
            BRANCO,
            pequena=True
        )
        texto(f"Restante: {metricas_tempo_real['custo_restante']}", col1_x, 326, BRANCO, pequena=True)
        texto(f"Nós expandidos: {metricas_tempo_real['nos_expandidos']}", col1_x, 343, BRANCO, pequena=True)
        texto(
            f"Progresso: {metricas_tempo_real['progresso']}%",
            col1_x,
            360,
            VERDE if modo_autonomo else CINZA,
            pequena=True
        )
    else:
        texto("Nenhum algoritmo executado ainda", col1_x, 258, CINZA, pequena=True)

    # -------------------------
    # Parâmetros interativos
    # -------------------------
    texto("PARÂMETROS INTERATIVOS", col1_x, 388, AZUL_CLARO)

    desenhar_botao_ajuste("Vel. manual", f"{vel_mov:.1f}", "vel_mov_menos", "vel_mov_mais", col1_x, 412, w=250)
    desenhar_botao_ajuste("Vel. auto", f"{vel_auto:.1f}", "vel_auto_menos", "vel_auto_mais", col1_x, 444, w=250)
    desenhar_botao_ajuste("Alcance", f"{int(alcance_sensor)} px", "alcance_menos", "alcance_mais", col1_x, 476, w=250)

    # -------------------------
    # Visualização
    # -------------------------
    texto("VISUALIZAÇÃO", col1_x, 515, AZUL_CLARO)

    rect_sensores = pygame.Rect(col1_x, 538, 250, 24)
    botoes_hud["toggle_sensores"] = rect_sensores
    pygame.draw.rect(tela, VERDE if mostrar_sensores else CINZA_ESCURO, rect_sensores, border_radius=6)
    texto(f"Sensores: {'ON' if mostrar_sensores else 'OFF'}", col1_x + 10, 543, BRANCO, pequena=True)

    rect_ambiente = pygame.Rect(col1_x, 568, 250, 24)
    botoes_hud["toggle_ambiente"] = rect_ambiente
    pygame.draw.rect(tela, VERDE if mostrar_ambiente_real else CINZA_ESCURO, rect_ambiente, border_radius=6)
    texto(f"Ambiente real: {'ON' if mostrar_ambiente_real else 'OFF'}", col1_x + 10, 573, BRANCO, pequena=True)

    rect_ruido = pygame.Rect(col1_x, 598, 250, 24)
    botoes_hud["toggle_ruido"] = rect_ruido
    pygame.draw.rect(tela, VERDE if ruido_sensor else CINZA_ESCURO, rect_ruido, border_radius=6)
    texto(f"Ruído: {'ON' if ruido_sensor else 'OFF'}", col1_x + 10, 603, BRANCO, pequena=True)

    rect_mapa = pygame.Rect(col1_x, 628, 250, 24)
    botoes_hud["toggle_mapa"] = rect_mapa
    pygame.draw.rect(tela, PAINEL_2, rect_mapa, border_radius=6)
    texto(f"Modo mapa: {modo_mapa}", col1_x + 10, 633, BRANCO, pequena=True)

    # -------------------------
    # Coluna direita
    # -------------------------
    desenhar_minimapa()
    desenhar_legenda(col2_x, 255)

    # Planejamento fica abaixo da legenda
    desenhar_comparativo(col2_x, 410)

    # Resultados abaixo dos botões
    texto("RESULTADOS", col2_x, 660, AZUL_CLARO)
    yy = 682
    yy = desenhar_metricas_algoritmo("Dijkstra", col2_x, yy)
    yy = desenhar_metricas_algoritmo("A*", col2_x, yy)

    # Teclado em coluna separada, mais à direita
    teclado_x = 1355

    texto("TECLADO", teclado_x, 95, AZUL_CLARO)

    teclado = [
        "W/↑ avançar",
        "S/↓ voltar",
        "A/← girar esq.",
        "D/→ girar dir.",
        "1 Dijkstra",
        "2 A*",
        "G iniciar",
        "Espaço parar",
        "R reset",
        "C limpar obs.",
        "P pausar",
        "V sensores",
        "T ambiente",
        "N ruído",
        "M mapa",
        "H ajuda",
        "ESC sair"
    ]

    yy = 120
    for linha in teclado:
        texto(linha, teclado_x, yy, CINZA, pequena=True)
        yy += 17

def desenhar_ajuda():
    if not mostrar_ajuda:
        return

    x, y = 55, 95
    largura, altura = 430, 330

    pygame.draw.rect(tela, (20, 28, 38), (x, y, largura, altura), border_radius=12)
    pygame.draw.rect(tela, AZUL_CLARO, (x, y, largura, 34), border_radius=12)

    texto("Atividade para Alunos", x + 15, y + 7, PRETO, pequena=True)

    linhas = [
        "Objetivo: comparar Dijkstra e A*.",
        "O robô recalcula a rota se detectar obstáculo.",
        "",
        "Clique direito: definir início",
        "Clique esquerdo: definir destino",
        "Clique meio: adicionar obstáculo extra",
        "Use o HUD para escolher algoritmo e iniciar",
        "Espaço: parar navegação autônoma",
        "WASD / Setas: controle manual",
        "R: resetar",
        "P: pausar",
        "V: sensores ON/OFF",
        "T: ambiente real ON/OFF",
        "N: ruído ON/OFF",
        "M: alternar visualização",
        "H: ocultar ajuda",
    ]

    yy = y + 48

    for linha in linhas:
        texto(linha, x + 15, yy, BRANCO, pequena=True)
        yy += 17


def desenhar_titulo():
    texto(
        "MiniROV Mapper - Dijkstra vs A* com Métricas em Tempo Real",
        45,
        22,
        BRANCO,
        titulo=True
    )
    texto(
        "Tempo, custo, nós expandidos e progresso atualizados durante a navegação",
        45,
        50,
        CINZA,
        pequena=True
    )


def resetar():
    global rov_x, rov_y, rov_ang, caminho, mapa
    global ponto_inicio, ponto_destino, caminho_planejado, metricas
    global metricas_tempo_real
    global modo_autonomo, indice_rota, status_rota, replanejamentos
    global obstaculos_extra

    rov_x, rov_y = 120, 140
    rov_ang = 0
    caminho = []
    mapa = [[DESCONHECIDO for _ in range(COLS)] for _ in range(ROWS)]

    ponto_inicio = None
    ponto_destino = None
    caminho_planejado = []

    modo_autonomo = False
    indice_rota = 0
    status_rota = "Nenhuma rota calculada"
    replanejamentos = 0

    obstaculos_extra = []

    metricas = {
        "Dijkstra": None,
        "A*": None
    }

    metricas_tempo_real = {
        "ativo": False,
        "algoritmo": None,
        "tempo_inicio_execucao": 0,
        "tempo_execucao_s": 0,
        "tempo_busca_ms": 0,
        "custo_total": 0,
        "custo_atual": 0,
        "custo_restante": 0,
        "nos_expandidos": 0,
        "progresso": 0
    }


rodando = True
leituras = {}

while rodando:
    clock.tick(FPS)

    for evento in pygame.event.get():
        if evento.type == pygame.QUIT:
            rodando = False

        if evento.type == pygame.MOUSEBUTTONDOWN:

            if processar_clique_hud(evento.pos):
                continue

            pos_grid = mouse_para_grid(evento.pos)

            if pos_grid:
                if evento.button == 1 and not celula_bloqueada(*pos_grid):
                    ponto_destino = pos_grid

                    if ponto_inicio is None:
                        atual = mundo_para_grid(rov_x, rov_y)
                        if atual:
                            ponto_inicio = encontrar_celula_livre_mais_proxima(*atual)

                    status_rota = "Destino definido. Escolha algoritmo e clique em INICIAR."

                elif evento.button == 3 and not celula_bloqueada(*pos_grid):
                    celula_segura = encontrar_celula_livre_mais_proxima(*pos_grid)

                    if celula_segura:
                        ponto_inicio = celula_segura
                        rov_x, rov_y = grid_para_mundo(*ponto_inicio)
                        modo_autonomo = False
                        indice_rota = 0
                        status_rota = "Início definido. Escolha destino."

                elif evento.button == 2:
                    adicionar_obstaculo_grid(*pos_grid)

                    if modo_autonomo:
                        replanejar_por_obstaculo()

        if evento.type == pygame.KEYDOWN:
            if evento.key == pygame.K_ESCAPE:
                rodando = False

            elif evento.key == pygame.K_SPACE:
                modo_autonomo = False
                status_rota = "Navegação autônoma parada"

            elif evento.key == pygame.K_r:
                resetar()

            elif evento.key == pygame.K_c:
                obstaculos_extra = []
                status_rota = "Obstáculos extras limpos"

                if ponto_destino is not None:
                    ponto_inicio = mundo_para_grid(rov_x, rov_y)
                    calcular_rota_atual(iniciar_auto=False)

            elif evento.key == pygame.K_p:
                pausado = not pausado

            elif evento.key == pygame.K_v:
                mostrar_sensores = not mostrar_sensores

            elif evento.key == pygame.K_t:
                mostrar_ambiente_real = not mostrar_ambiente_real

            elif evento.key == pygame.K_n:
                ruido_sensor = not ruido_sensor

            elif evento.key == pygame.K_h:
                mostrar_ajuda = not mostrar_ajuda

            elif evento.key == pygame.K_m:
                modo_mapa += 1
                if modo_mapa > 3:
                    modo_mapa = 1

            elif evento.key == pygame.K_1:
                algoritmo_atual = "Dijkstra"
                status_rota = "Dijkstra selecionado. Pressione G para testar."

            elif evento.key == pygame.K_2:
                algoritmo_atual = "A*"
                status_rota = "A* selecionado. Pressione G para testar."

            elif evento.key == pygame.K_g:
                ponto_inicio = mundo_para_grid(rov_x, rov_y)
                calcular_rota_atual(iniciar_auto=True)

            elif evento.key == pygame.K_EQUALS or evento.key == pygame.K_KP_PLUS:
                vel_mov = min(8, vel_mov + 0.5)

            elif evento.key == pygame.K_MINUS or evento.key == pygame.K_KP_MINUS:
                vel_mov = max(1, vel_mov - 0.5)

            elif evento.key == pygame.K_RIGHTBRACKET:
                alcance_sensor = min(350, alcance_sensor + 20)

            elif evento.key == pygame.K_LEFTBRACKET:
                alcance_sensor = max(80, alcance_sensor - 20)

    if not pausado:
        teclas = pygame.key.get_pressed()

        if modo_autonomo:
            mover_robo_autonomo()
            atualizar_metricas_tempo_real()

        else:
            if teclas[pygame.K_a] or teclas[pygame.K_LEFT]:
                rov_ang -= vel_rot

            if teclas[pygame.K_d] or teclas[pygame.K_RIGHT]:
                rov_ang += vel_rot

            novo_x, novo_y = rov_x, rov_y

            if teclas[pygame.K_w] or teclas[pygame.K_UP]:
                novo_x += math.cos(math.radians(rov_ang)) * vel_mov
                novo_y += math.sin(math.radians(rov_ang)) * vel_mov

            if teclas[pygame.K_s] or teclas[pygame.K_DOWN]:
                novo_x -= math.cos(math.radians(rov_ang)) * vel_mov
                novo_y -= math.sin(math.radians(rov_ang)) * vel_mov

            if not colisao(novo_x, novo_y):
                rov_x, rov_y = novo_x, novo_y

        caminho.append((int(rov_x), int(rov_y)))

        if len(caminho) > 1200:
            caminho.pop(0)

        leituras = atualizar_mapeamento()

    else:
        leituras = atualizar_mapeamento()

    tela.fill(FUNDO)

    if modo_mapa == 1:
        desenhar_mapa_construido()
        if mostrar_ambiente_real:
            desenhar_tanque_real()

    elif modo_mapa == 2:
        desenhar_mapa_construido()

    elif modo_mapa == 3:
        desenhar_tanque_real()

    desenhar_caminho()
    desenhar_sensores()
    desenhar_caminho_planejado()
    desenhar_pontos_rota()
    desenhar_rov()
    desenhar_titulo()
    desenhar_ajuda()
    desenhar_hud(leituras)

    if pausado:
        pygame.draw.rect(tela, (0, 0, 0), (300, 300, 300, 70), border_radius=12)
        texto("SIMULAÇÃO PAUSADA", 330, 322, AMARELO, titulo=True)

    pygame.display.flip()

pygame.quit()