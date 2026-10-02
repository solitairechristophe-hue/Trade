import datetime as dt
import json

from conftest import ticket_dict

from executor.config import Config
from executor.main import cycle
from executor.state import Etat


class FauxCourtier:
    def __init__(self):
        self.ordres = {}  # ref -> [statut, prix]
        self.envois = []
        self.cot = (3.0, 3.2)
        self.prix_action = 43.0

    def nav(self):
        return 10_000.0

    def placer_entree(self, t, ref_e, ref_tp):
        self.ordres[ref_e] = ["Submitted", 0]
        self.ordres[ref_tp] = ["PreSubmitted", 0]
        self.envois.append(("entree", t.id))

    def placer_sortie(self, t, prix, ref):
        self.ordres[ref] = ["Submitted", 0]
        self.envois.append(("sortie", ref, prix))

    def annuler(self, ref):
        if ref in self.ordres:
            self.ordres[ref][0] = "Cancelled"

    def statut(self, ref):
        o = self.ordres.get(ref)
        return (o[0], o[1]) if o else None

    def cotation(self, t):
        return self.cot

    def cours(self, s):
        return self.prix_action


def preparer(tmp_path, **cfg):
    d = tmp_path / "tickets"
    d.mkdir(parents=True)
    (d / "2026-10-02-swing.json").write_text(json.dumps({"run_date": "2026-10-02", "desk": "swing",
                                                         "tickets": [ticket_dict()]}))
    c = Config(tickets_dir=d, state_file=tmp_path / "etat.sqlite", kill_switch_file=tmp_path / "STOP",
               dry_run=cfg.pop("dry_run", False), **cfg)
    return c, Etat(c.state_file), FauxCourtier(), []


def m(h, mi=0, jour=2):
    return dt.datetime(2026, 10, jour, h, mi)


def test_cycle_complet_sl(tmp_path):
    cfg, etat, br, msgs = preparer(tmp_path)
    note = lambda x, urgent=False: msgs.append(x)
    cycle(cfg, br, etat, note, m(3))  # avant l'ouverture : ordre DAY envoyé
    assert br.envois == [("entree", "swing-2026-10-02-SMCI")]
    cycle(cfg, br, etat, note, m(3, 1))  # pas de double envoi
    assert len(br.envois) == 1

    br.ordres["swing-2026-10-02-SMCI:entree"] = ["Filled", 3.15]
    cycle(cfg, br, etat, note, m(10))
    assert etat.actifs()[0].statut == "OUVERT"

    br.cot = (1.4, 1.6)  # milieu 1,50 ≤ SL 1,60
    cycle(cfg, br, etat, note, m(11))
    assert br.ordres["swing-2026-10-02-SMCI:tp"][0] == "Cancelled"
    assert br.envois[-1] == ("sortie", "swing-2026-10-02-SMCI:sortie1", 1.4)

    for _ in range(cfg.exit_reprice_loops):  # non exécuté : recotation
        cycle(cfg, br, etat, note, m(11, 5))
    assert br.envois[-1][1] == "swing-2026-10-02-SMCI:sortie2"

    br.ordres["swing-2026-10-02-SMCI:sortie2"] = ["Filled", 1.4]
    cycle(cfg, br, etat, note, m(11, 10))
    assert etat.actifs() == []
    assert any(x.startswith("CLOS") for x in msgs)


def test_tp_natif(tmp_path):
    cfg, etat, br, msgs = preparer(tmp_path)
    note = lambda x, urgent=False: msgs.append(x)
    cycle(cfg, br, etat, note, m(3))
    br.ordres["swing-2026-10-02-SMCI:entree"] = ["Filled", 3.15]
    cycle(cfg, br, etat, note, m(10))
    br.cot = (6.2, 6.4)
    cycle(cfg, br, etat, note, m(11))  # TP atteint mais l'ordre TP IBKR travaille : rien à faire
    assert len(br.envois) == 1
    br.ordres["swing-2026-10-02-SMCI:tp"] = ["Filled", 6.1]
    cycle(cfg, br, etat, note, m(11, 1))
    assert etat.actifs() == []


def test_simulation_et_arret(tmp_path):
    cfg, etat, br, msgs = preparer(tmp_path, dry_run=True)
    cycle(cfg, br, etat, lambda x, urgent=False: msgs.append(x), m(3))
    assert br.envois == [] and msgs[0].startswith("SIMULATION")

    cfg2, etat2, br2, _ = preparer(tmp_path / "b")
    cfg2.kill_switch_file.write_text("")
    cycle(cfg2, br2, etat2, lambda x, urgent=False: None, m(3))
    assert br2.envois == []


def test_entree_non_executee_expire(tmp_path):
    cfg, etat, br, msgs = preparer(tmp_path)
    cycle(cfg, br, etat, lambda x, urgent=False: msgs.append(x), m(3))
    br.ordres.clear()  # redémarrage : l'ordre du jour n'existe plus
    cycle(cfg, br, etat, lambda x, urgent=False: msgs.append(x), m(3, 0, 5))
    assert etat.actifs() == [] and any(x.startswith("EXPIRÉ") for x in msgs)


def test_partiel_et_sans_cotation(tmp_path):
    cfg, etat, br, msgs = preparer(tmp_path)
    note = lambda x, urgent=False: msgs.append(x)
    cycle(cfg, br, etat, note, m(3))
    br.ordres["swing-2026-10-02-SMCI:entree"] = ["Filled", 2.8]
    cycle(cfg, br, etat, note, m(10))
    br.cot = (None, None)
    cycle(cfg, br, etat, note, m(11))
    cycle(cfg, br, etat, note, m(11, 1))
    assert sum(x.startswith("Pas de cotation") for x in msgs) == 1  # une alerte par jour

    cfg2, etat2, br2, msgs2 = preparer(tmp_path / "b")
    cycle(cfg2, br2, etat2, lambda x, urgent=False: msgs2.append(x), m(3))
    br2.ordres["swing-2026-10-02-SMCI:entree"] = ["Cancelled", 2.8]
    cycle(cfg2, br2, etat2, lambda x, urgent=False: msgs2.append(x), m(16, 5))
    assert etat2.actifs() == [] and br2.ordres["swing-2026-10-02-SMCI:tp"][0] == "Cancelled"
    assert any(x.startswith("À VÉRIFIER") for x in msgs2)
