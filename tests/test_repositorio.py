from app.repositorio import CONTAS, MOVIMENTACOES, USUARIOS, Repositorio


def test_ler_arquivo_inexistente_devolve_lista_vazia(tmp_path):
    assert Repositorio(tmp_path).ler("nada.json") == []


def test_gravar_e_ler_com_acentos(tmp_path):
    repo = Repositorio(tmp_path / "dados")
    repo.gravar("x.json", [{"nome": "João"}])
    assert repo.ler("x.json") == [{"nome": "João"}]
    assert "João" in (tmp_path / "dados" / "x.json").read_text(encoding="utf-8")


def test_gravacao_atomica_nao_deixa_temporarios(tmp_path):
    repo = Repositorio(tmp_path)
    for i in range(3):
        repo.gravar("x.json", [i])
    assert [p.name for p in tmp_path.iterdir()] == ["x.json"]


def test_carga_inicial_cria_base_consistente(srv):
    repo = srv.repo
    assert repo.existe_base()
    usuarios = repo.ler(USUARIOS)
    assert {u["perfil"] for u in usuarios} == {"cliente", "atendente", "aprovador"}
    for conta in repo.ler(CONTAS):
        movs = repo.movimentacoes(conta["conta"])
        assert movs[-1]["saldo_apos_centavos"] == conta["saldo_centavos"]
    assert len([m for m in repo.ler(MOVIMENTACOES) if m["conta"] == "0001-1" and m["tipo"] == "SAQUE"]) == 10


def test_pin_nunca_em_texto_puro(srv):
    conteudo = srv.repo.caminho(USUARIOS).read_text(encoding="utf-8")
    for pin in ("1111", "2222", "3333", "4444"):
        assert f'"{pin}"' not in conteudo
    assert all(u["pin_hash"] and u["pin_salt"] for u in srv.repo.ler(USUARIOS))


def test_registrar_movimentacao_atualiza_saldo(srv):
    srv.repo.registrar_movimentacao(
        {"id": "x", "conta": "0002-2", "data_hora": "2026-11-07T15:00:00-03:00", "tipo": "DEPOSITO",
         "valor_centavos": 100, "saldo_apos_centavos": 300_100}
    )
    assert srv.repo.buscar_conta("0002-2")["saldo_centavos"] == 300_100
