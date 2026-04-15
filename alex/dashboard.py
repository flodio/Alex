"""
Dashboard Streamlit pour visualiser les trades, analyses SMC et patterns.
Lancer avec : streamlit run alex/dashboard.py (depuis le dossier racine du projet)
"""

import json
import sys
import os

# Permet d'importer les modules alex directement
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import database as db

# ---------------------------------------------------------------------------
# Configuration de la page
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Alex — SMC Trading Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialisation de la base si nécessaire
db.initialiser_base()


# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------
st.sidebar.title("📊 Alex — SMC Analyzer")
page = st.sidebar.radio(
    "Navigation",
    [
        "📋 Trades",
        "🔍 Analyse SMC",
        "📈 Patterns",
        "🔐 Confirmations Cachées",
    ],
)

st.sidebar.markdown("---")
st.sidebar.caption("Version 1.0 — XAUUSD Trading Tool")


# ---------------------------------------------------------------------------
# Page 1 — Trades
# ---------------------------------------------------------------------------
def page_trades():
    st.title("📋 Trades")
    st.markdown("Vue d'ensemble de tous les signaux extraits et parsés.")

    trades = db.lire_tous_trades()
    if not trades:
        st.info("Aucun trade en base de données. Lancez d'abord `python main.py`.")
        return

    df = pd.DataFrame(trades)

    # Filtres
    col1, col2, col3 = st.columns(3)
    with col1:
        direction_filtre = st.selectbox(
            "Direction", ["Toutes", "BUY", "SELL"]
        )
    with col2:
        resultat_filtre = st.selectbox(
            "Résultat", ["Tous", "Gagnant", "Perdant", "Inconnu"]
        )
    with col3:
        conf_min = st.slider("Confiance minimum", 0.0, 1.0, 0.5, 0.05)

    # Application des filtres
    df_filtre = df.copy()
    if direction_filtre != "Toutes":
        df_filtre = df_filtre[df_filtre["direction"] == direction_filtre]
    if resultat_filtre == "Gagnant":
        df_filtre = df_filtre[df_filtre["resultat"] == 1]
    elif resultat_filtre == "Perdant":
        df_filtre = df_filtre[df_filtre["resultat"] == 0]
    elif resultat_filtre == "Inconnu":
        df_filtre = df_filtre[df_filtre["resultat"].isna()]
    if "confidence" in df_filtre.columns:
        df_filtre = df_filtre[df_filtre["confidence"].fillna(0) >= conf_min]

    st.markdown(f"**{len(df_filtre)} trade(s) affichés** sur {len(df)} total")

    # Colonnes à afficher
    cols_affichage = [
        c for c in [
            "id", "timestamp", "direction", "entry_min", "entry_max",
            "tp1", "tp2", "tp3", "sl", "confidence", "resultat"
        ]
        if c in df_filtre.columns
    ]
    st.dataframe(df_filtre[cols_affichage], use_container_width=True)

    # Statistiques rapides
    st.markdown("---")
    st.subheader("Statistiques")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total trades", len(df))
    with c2:
        n_g = int(df["resultat"].sum()) if "resultat" in df.columns else 0
        st.metric("Gagnants", n_g)
    with c3:
        n_p = int((df["resultat"] == 0).sum()) if "resultat" in df.columns else 0
        st.metric("Perdants", n_p)
    with c4:
        win_rate = n_g / (n_g + n_p) if (n_g + n_p) > 0 else 0
        st.metric("Win Rate", f"{win_rate:.1%}")

    # Graphique répartition directions
    if "direction" in df.columns:
        fig = px.pie(
            df, names="direction",
            title="Répartition BUY / SELL",
            color_discrete_sequence=["#00cc44", "#ff4444"],
        )
        st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Page 2 — Analyse SMC
# ---------------------------------------------------------------------------
def page_smc():
    st.title("🔍 Analyse SMC par Trade")
    st.markdown("Détail des confirmations SMC/ICT pour chaque trade.")

    analyses = db.lire_analyses_smc()
    if not analyses:
        st.info("Aucune analyse SMC disponible. Lancez d'abord `python main.py`.")
        return

    df = pd.DataFrame(analyses)

    # Tableau avec couleurs conditionnelles
    colonnes_bool = [
        "choch_present", "bos_present", "ob_in_zone",
        "fvg_in_zone", "liquidity_swept",
    ]
    cols_affichage = [
        c for c in [
            "trade_id", "direction", "timestamp", "session",
            "premium_discount", "fibonacci_level",
            *colonnes_bool, "confirmations_count", "resultat"
        ]
        if c in df.columns
    ]

    st.dataframe(df[cols_affichage], use_container_width=True)

    # Graphique taux de présence par confirmation
    st.subheader("Taux de présence des confirmations SMC")
    taux_presence = {
        col: df[col].mean() if col in df.columns else 0
        for col in colonnes_bool
    }
    fig_bar = px.bar(
        x=list(taux_presence.keys()),
        y=list(taux_presence.values()),
        labels={"x": "Confirmation", "y": "Taux de présence"},
        title="Présence des confirmations SMC sur tous les trades",
        color=list(taux_presence.values()),
        color_continuous_scale="RdYlGn",
        range_color=[0, 1],
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    # Répartition des sessions
    if "session" in df.columns:
        fig_session = px.pie(
            df, names="session",
            title="Répartition des sessions",
        )
        st.plotly_chart(fig_session, use_container_width=True)


# ---------------------------------------------------------------------------
# Page 3 — Patterns
# ---------------------------------------------------------------------------
def page_patterns():
    st.title("📈 Patterns Détectés")
    st.markdown("Analyse statistique comparant trades gagnants vs perdants.")

    rapport = db.lire_dernier_rapport()
    if not rapport:
        st.info("Aucun rapport de patterns disponible. Lancez d'abord `python main.py`.")
        return

    # Métriques principales
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total trades", rapport.get("total_trades", 0))
    with c2:
        st.metric("Trades gagnants", rapport.get("winning_trades", 0))
    with c3:
        st.metric("Trades perdants", rapport.get("losing_trades", 0))
    with c4:
        wr = rapport.get("win_rate", 0)
        st.metric("Win Rate", f"{wr:.1%}")

    strategie = rapport.get("confirmed_strategy", {})

    st.markdown("---")
    st.subheader("Stratégie confirmée")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Toujours présent dans les trades gagnants :**")
        for conf in strategie.get("always_present_in_wins", []):
            st.success(f"✅ {conf}")

        st.markdown("**Souvent présent dans les trades gagnants :**")
        for conf in strategie.get("often_present_in_wins", []):
            st.info(f"ℹ️ {conf}")

    with col2:
        st.markdown("**Préférences détectées :**")
        st.markdown(f"- Session : **{strategie.get('time_preference', 'N/A')}**")
        st.markdown(f"- Fibonacci : **{strategie.get('fibonacci_preference', 'N/A')}**")
        st.markdown(
            f"- Premium/Discount : **{strategie.get('premium_discount_preference', 'N/A')}**"
        )

    # Confluences niveaux ronds
    confluence = rapport.get("confluence_niveaux_ronds", {})
    if confluence.get("significatif"):
        st.success(
            f"📍 Confluences avec niveaux ronds détectées "
            f"({confluence.get('taux', 0):.1%} des trades gagnants)"
        )

    # Rapport JSON brut
    with st.expander("Rapport JSON complet"):
        st.json(rapport)


# ---------------------------------------------------------------------------
# Page 4 — Confirmations Cachées
# ---------------------------------------------------------------------------
def page_confirmations_cachees():
    st.title("🔐 Confirmations Cachées")
    st.markdown(
        "Confirmations probables non documentées détectées par reverse-engineering."
    )

    rapport = db.lire_dernier_rapport()
    if not rapport:
        st.info("Aucun rapport disponible. Lancez d'abord `python main.py`.")
        return

    cachees = rapport.get("hidden_confirmations", [])
    if not cachees:
        st.warning(
            "Aucune confirmation cachée détectée pour le moment. "
            "Plus de données sont nécessaires."
        )
        return

    for conf in cachees:
        confiance = conf.get("confiance", 0)
        couleur = "🟢" if confiance > 0.7 else "🟡" if confiance > 0.4 else "🔴"
        with st.expander(f"{couleur} {conf.get('nom', 'Inconnu')} — Confiance : {confiance:.1%}"):
            st.markdown(f"**Description :** {conf.get('description', '')}")

            # Tableau comparatif gagnants vs perdants si disponible
            details = {
                k: v
                for k, v in conf.items()
                if k not in ("nom", "description", "confiance")
            }
            if details:
                st.json(details)

    # Graphique des confiances
    if cachees:
        fig = px.bar(
            x=[c.get("nom", "") for c in cachees],
            y=[c.get("confiance", 0) for c in cachees],
            labels={"x": "Confirmation", "y": "Confiance"},
            title="Niveau de confiance des confirmations cachées",
            color=[c.get("confiance", 0) for c in cachees],
            color_continuous_scale="RdYlGn",
            range_color=[0, 1],
        )
        st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------
if page == "📋 Trades":
    page_trades()
elif page == "🔍 Analyse SMC":
    page_smc()
elif page == "📈 Patterns":
    page_patterns()
elif page == "🔐 Confirmations Cachées":
    page_confirmations_cachees()
