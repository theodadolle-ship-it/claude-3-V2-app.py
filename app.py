
import streamlit as st
import pandas as pd
import sqlite3
import json
import re
import statistics
from datetime import datetime
from pathlib import Path

# =========================================================
# CONFIGURATION
# =========================================================

APP_NAME = "Vinted Deal Finder V2"
DB_PATH = "vinted_deal_finder.db"

CATEGORIES = [
    "Vêtements", "Chaussures", "Sacs et accessoires",
    "Beauté et soins", "Maison et décoration",
    "Jeux vidéo", "Jouets et jeux", "Livres",
    "Collections", "Sport", "Électronique",
    "Bébé et enfants", "Vintage", "Autres"
]

POPULAR_PRODUCTS = [
    "Nike Air Force 1", "Nike Air Max", "Nike Dunk",
    "Adidas Samba", "Adidas Gazelle", "New Balance 530",
    "Jordan 1", "Salomon XT-6", "Dr Martens",
    "Nike Tech Fleece", "Carhartt WIP", "Dickies",
    "Levi's 501", "Ralph Lauren", "Lacoste",
    "The North Face", "Patagonia", "Arc'teryx",
    "Stone Island", "Tommy Hilfiger", "Sandro",
    "Maje", "Longchamp", "Michael Kors",
    "Lego", "Pokémon", "Nintendo Switch",
    "PlayStation", "Jeux vidéo", "Figurines",
    "Cartes à collectionner", "Vases", "Décoration vintage",
    "Lampes", "Objets design", "Montres"
]

DEFECT_WORDS = [
    "trou", "tache", "tâche", "taché", "déchiré",
    "dechire", "défaut", "defaut", "usé", "use ",
    "bouloche", "bouloché", "décoloré", "decolore",
    "abîmé", "abime", "cassé", "casse", "fissure",
    "rayure", "manque une pièce", "incomplet",
    "ne fonctionne pas", "à réparer", "a reparer"
]

SUSPICIOUS_WORDS = [
    "réplique", "replique", "contrefaçon",
    "contrefacon", "fake", "imitation", "copie"
]

ACCEPTED_CONDITIONS = [
    "Neuf avec étiquette",
    "Neuf sans étiquette",
    "Très bon état"
]


# =========================================================
# BASE DE DONNÉES
# =========================================================

def get_db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS deals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date_added TEXT,
                title TEXT,
                category TEXT,
                brand TEXT,
                size TEXT,
                condition_name TEXT,
                description TEXT,
                purchase_price REAL,
                buyer_fees REAL,
                inbound_shipping REAL,
                packaging REAL,
                resale_estimate REAL,
                resale_evidence TEXT,
                confidence TEXT,
                url TEXT,
                status TEXT DEFAULT 'À étudier',
                sale_price REAL DEFAULT 0,
                sale_fees REAL DEFAULT 0,
                other_costs REAL DEFAULT 0,
                notes TEXT
            )
        """)
        conn.commit()


def save_deal(data):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO deals (
                date_added, title, category, brand, size,
                condition_name, description, purchase_price,
                buyer_fees, inbound_shipping, packaging,
                resale_estimate, resale_evidence, confidence,
                url, status, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            data["title"], data["category"], data["brand"],
            data["size"], data["condition"], data["description"],
            data["purchase"], data["buyer_fees"],
            data["shipping"], data["packaging"],
            data["resale"], data["evidence"],
            data["confidence"], data["url"],
            data["status"], data["notes"]
        ))
        conn.commit()


def load_deals():
    with get_db() as conn:
        return pd.read_sql_query(
            "SELECT * FROM deals ORDER BY id DESC", conn
        )


def update_sale(deal_id, sale_price, sale_fees, other_costs):
    with get_db() as conn:
        conn.execute("""
            UPDATE deals
            SET status = 'Vendu',
                sale_price = ?,
                sale_fees = ?,
                other_costs = ?
            WHERE id = ?
        """, (sale_price, sale_fees, other_costs, deal_id))
        conn.commit()


def delete_deal(deal_id):
    with get_db() as conn:
        conn.execute("DELETE FROM deals WHERE id = ?", (deal_id,))
        conn.commit()


# =========================================================
# ANALYSE DES ANNONCES
# =========================================================

def inspect_description(description, condition):
    text = (description or "").lower()
    defects = [word for word in DEFECT_WORDS if word in text]
    suspicious = [
        word for word in SUSPICIOUS_WORDS if word in text
    ]

    if suspicious:
        return "À REJETER", defects, suspicious

    if defects:
        return "À VÉRIFIER", defects, suspicious

    if condition not in ACCEPTED_CONDITIONS:
        return "À VÉRIFIER", defects, suspicious

    return "ÉTAT À CONFIRMER", defects, suspicious


def estimate_resale(comparable_prices, discount):
    prices = [
        float(p) for p in comparable_prices
        if p is not None and float(p) > 0
    ]

    if not prices:
        return None, "Aucune donnée", 0

    median = statistics.median(prices)
    estimate = median * discount

    if len(prices) >= 10:
        confidence = "Élevée"
    elif len(prices) >= 5:
        confidence = "Moyenne"
    else:
        confidence = "Faible"

    return round(estimate, 2), confidence, len(prices)


def calculate_profit(
    resale, purchase, buyer_fees, shipping, packaging,
    sale_fees=0, other_costs=0
):
    total_cost = (
        purchase + buyer_fees + shipping +
        packaging + sale_fees + other_costs
    )
    profit = resale - total_cost
    margin = (profit / total_cost * 100) if total_cost > 0 else 0
    return round(profit, 2), round(margin, 1), round(total_cost, 2)


def opportunity_score(profit, margin, confidence, condition):
    score = 0

    if profit > 30:
        score += 35
    elif profit > 15:
        score += 25
    elif profit > 5:
        score += 15
    elif profit > 0:
        score += 5

    if margin >= 100:
        score += 25
    elif margin >= 50:
        score += 20
    elif margin >= 25:
        score += 10

    if confidence == "Élevée":
        score += 20
    elif confidence == "Moyenne":
        score += 12
    elif confidence == "Faible":
        score += 5

    if condition == "ÉTAT À CONFIRMER":
        score += 10

    return min(score, 100)


def opportunity_label(score):
    if score >= 75:
        return "Excellente opportunité"
    if score >= 55:
        return "Opportunité intéressante"
    if score >= 35:
        return "À étudier"
    return "Potentiel faible"


# =========================================================
# INTERFACE
# =========================================================

st.set_page_config(
    page_title=APP_NAME,
    page_icon="🔎",
    layout="wide"
)

init_db()

st.title("🔎 Vinted Deal Finder V2")
st.caption(
    "Détection, analyse et suivi des opportunités d'achat-revente."
)

with st.sidebar:
    st.header("⚙️ Paramètres")

    budget_max = st.number_input(
        "Budget maximum par article (€)",
        min_value=1.0,
        max_value=10000.0,
        value=100.0,
        step=5.0
    )

    min_profit = st.number_input(
        "Bénéfice minimum souhaité (€)",
        min_value=0.0,
        value=10.0,
        step=1.0
    )

    min_margin = st.number_input(
        "Marge minimum souhaitée (%)",
        min_value=0.0,
        value=30.0,
        step=5.0
    )

    discount = st.slider(
        "Coefficient prudent de revente",
        min_value=0.50,
        max_value=1.00,
        value=0.85,
        step=0.05
    )

    st.caption(
        "Le coefficient réduit les prix comparables saisis. "
        "Il ne transforme pas des prix affichés en prix de ventes réelles."
    )

# =========================================================
# ONGLETS
# =========================================================

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔍 Recherche",
    "➕ Ajouter une annonce",
    "📊 Opportunités",
    "📦 Historique",
    "📈 Statistiques"
])


# =========================================================
# ONGLET 1 : RECHERCHE
# =========================================================

with tab1:
    st.header("Exploration des catégories")

    st.info(
        "Cette interface prépare tes recherches. "
        "La récupération automatique des annonces nécessite "
        "une source de données autorisée."
    )

    selected_categories = st.multiselect(
        "Catégories à explorer",
        CATEGORIES,
        default=CATEGORIES
    )

    st.subheader("Produits populaires")

    selected_products = st.multiselect(
        "Produits à surveiller",
        POPULAR_PRODUCTS,
        default=POPULAR_PRODUCTS[:12]
    )

    custom_search = st.text_input(
        "Ajouter un produit ou une marque"
    )

    if st.button("Préparer mes recherches", type="primary"):
        searches = selected_products.copy()

        if custom_search.strip():
            searches.append(custom_search.strip())

        st.session_state["search_plan"] = {
            "categories": selected_categories,
            "products": searches
        }

        st.success(
            f"{len(selected_categories)} catégories et "
            f"{len(searches)} recherches préparées."
        )

    if "search_plan" in st.session_state:
        st.subheader("Plan de recherche")
        st.write(
            "Catégories :",
            ", ".join(st.session_state["search_plan"]["categories"])
        )
        st.write(
            "Produits :",
            ", ".join(st.session_state["search_plan"]["products"])
        )

    st.divider()

    st.subheader("Importer des annonces depuis un CSV")

    uploaded_csv = st.file_uploader(
        "Importer un fichier CSV d'annonces",
        type=["csv"]
    )

    if uploaded_csv:
        try:
            imported = pd.read_csv(uploaded_csv, sep=None, engine="python")
            st.write("Aperçu des données importées")
            st.dataframe(imported.head(20), use_container_width=True)

            st.caption(
                "L'import sert à examiner les données. "
                "Les annonces ne sont pas enregistrées automatiquement."
            )

            st.download_button(
                "Télécharger le modèle CSV",
                pd.DataFrame(columns=[
                    "title", "category", "brand", "size",
                    "condition", "description", "purchase",
                    "url"
                ]).to_csv(index=False).encode("utf-8"),
                "modele_annonces.csv",
                "text/csv"
            )
        except Exception as e:
            st.error(f"Erreur de lecture du CSV : {e}")


# =========================================================
# ONGLET 2 : AJOUTER UNE ANNONCE
# =========================================================

with tab2:
    st.header("Ajouter une annonce à analyser")

    with st.form("add_deal_form"):
        title = st.text_input("Titre de l'article")
        category = st.selectbox("Catégorie", CATEGORIES)
        brand = st.text_input("Marque")
        size = st.text_input("Taille / modèle")

        condition = st.selectbox(
            "État annoncé",
            ACCEPTED_CONDITIONS + [
                "Bon état", "Satisfaisant", "Non précisé"
            ]
        )

        description = st.text_area(
            "Description de l'annonce",
            height=130
        )

        url = st.text_input("Lien de l'annonce Vinted")

        st.subheader("Coût d'achat")

        c1, c2 = st.columns(2)

        purchase = c1.number_input(
            "Prix de l'article (€)",
            min_value=0.0,
            value=0.0,
            step=1.0
        )

        buyer_fees = c2.number_input(
            "Frais acheteur (€)",
            min_value=0.0,
            value=0.0,
            step=0.5
        )

        c3, c4 = st.columns(2)

        shipping = c3.number_input(
            "Livraison à l'achat (€)",
            min_value=0.0,
            value=0.0,
            step=0.5
        )

        packaging = c4.number_input(
            "Emballage (€)",
            min_value=0.0,
            value=0.0,
            step=0.5
        )

        st.subheader("Comparables de revente")

        st.caption(
            "Entre des prix de comparaison pertinents, idéalement "
            "issus de ventes terminées vérifiables. "
            "Indique leur nature dans le champ de preuve."
        )

        comparable_text = st.text_input(
            "Prix comparables séparés par des virgules",
            placeholder="35, 39, 42, 40"
        )

        evidence = st.selectbox(
            "Nature des comparables",
            [
                "Prix affichés d'annonces actives",
                "Prix d'annonces marquées vendues",
                "Prix de ventes réellement observés",
                "Estimation personnelle",
                "Aucune preuve"
            ]
        )

        notes = st.text_area("Notes personnelles")

        submitted = st.form_submit_button(
            "Analyser et enregistrer",
            type="primary"
        )

    if submitted:
        if not title.strip():
            st.error("Indique le titre de l'article.")
        elif purchase <= 0:
            st.error("Indique un prix d'achat valide.")
        elif purchase > budget_max:
            st.error(
                f"Le prix dépasse ton budget actuel de {budget_max:.2f} €."
            )
        else:
            result, defects, suspicious = inspect_description(
                description, condition
            )

            try:
                comps = [
                    float(x.strip().replace(",", "."))
                    for x in comparable_text.split(",")
                    if x.strip()
                ]
            except ValueError:
                comps = []
                st.error("Vérifie les prix comparables.")
                st.stop()

            resale, confidence, comp_count = estimate_resale(
                comps, discount
            )

            profit = None
            margin = None

            if resale is not None:
                profit, margin, total_cost = calculate_profit(
                    resale, purchase, buyer_fees,
                    shipping, packaging
                )

            st.subheader("Résultat de l'analyse")

            if suspicious:
                st.error(
                    "Mots associés à une possible contrefaçon : "
                    + ", ".join(suspicious)
                )
            elif defects:
                st.warning(
                    "Défauts mentionnés : " + ", ".join(defects)
                )
            else:
                st.info(
                    "Aucun défaut détecté dans le texte. "
                    "Cela ne garantit pas l'état réel de l'article."
                )

            if resale is None:
                st.warning(
                    "Impossible d'estimer la revente : "
                    "aucun comparable fourni."
                )
                score = 0
            else:
                score = opportunity_score(
                    profit, margin, confidence, result
                )

                st.metric("Revente estimée", f"{resale:.2f} €")
                st.metric("Bénéfice net estimé", f"{profit:.2f} €")
                st.metric("Marge estimée", f"{margin:.1f} %")
                st.write(f"Comparables utilisés : {comp_count}")
                st.write(f"Confiance statistique : {confidence}")
                st.write(f"Score indicatif : {score}/100")
                st.write(opportunity_label(score))

                if evidence == "Prix affichés d'annonces actives":
                    st.warning(
                        "Attention : les prix affichés ne prouvent "
                        "pas que les articles se vendent à ces montants."
                    )

            if result == "À REJETER":
                st.error("Annonce à rejeter selon les mots détectés.")

            if st.button("Confirmer l'enregistrement"):
                save_deal({
                    "title": title,
                    "category": category,
                    "brand": brand,
                    "size": size,
                    "condition": condition,
                    "description": description,
                    "purchase": purchase,
                    "buyer_fees": buyer_fees,
                    "shipping": shipping,
                    "packaging": packaging,
                    "resale": resale or 0,
                    "evidence": evidence,
                    "confidence": confidence,
                    "url": url,
                    "status": "À étudier",
                    "notes": notes
                })
                st.success("Article enregistré dans ton historique.")


# =========================================================
# ONGLET 3 : OPPORTUNITÉS
# =========================================================

with tab3:
    st.header("Mes opportunités")

    deals = load_deals()

    if deals.empty:
        st.info("Aucune annonce enregistrée pour le moment.")
    else:
        opportunities = deals.copy()

        opportunities["benefice_estime"] = (
            opportunities["resale_estimate"]
            - opportunities["purchase_price"]
            - opportunities["buyer_fees"]
            - opportunities["inbound_shipping"]
            - opportunities["packaging"]
        )

        opportunities = opportunities[
            opportunities["status"] != "Vendu"
        ]

        opportunities = opportunities[
            opportunities["purchase_price"] <= budget_max
        ]

        opportunities = opportunities[
            opportunities["benefice_estime"] >= min_profit
        ]

        opportunities["marge_estimee"] = (
            opportunities["benefice_estime"] /
            (
                opportunities["purchase_price"]
                + opportunities["buyer_fees"]
                + opportunities["inbound_shipping"]
                + opportunities["packaging"]
            ).replace(0, pd.NA)
        ) * 100

        opportunities = opportunities[
            opportunities["marge_estimee"] >= min_margin
        ]

        st.write(f"{len(opportunities)} opportunités correspondent à tes critères.")

        if not opportunities.empty:
            st.dataframe(
                opportunities[[
                    "title", "category", "purchase_price",
                    "resale_estimate", "benefice_estime",
                    "marge_estimee", "confidence", "url"
                ]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "url": st.column_config.LinkColumn(
                        "Annonce", display_text="Ouvrir"
                    )
                }
            )
        else:
            st.info("Aucune opportunité ne correspond à tes critères.")


# =========================================================
# ONGLET 4 : HISTORIQUE
# =========================================================

with tab4:
    st.header("Historique de tes articles")

    history = load_deals()

    if history.empty:
        st.info("Ton historique est encore vide.")
    else:
        st.dataframe(
            history[[
                "id", "date_added", "title", "category",
                "purchase_price", "resale_estimate",
                "status", "sale_price"
            ]],
            use_container_width=True,
            hide_index=True
        )

        st.divider()

        st.subheader("Enregistrer une vente")

        available = history[
            history["status"] != "Vendu"
        ]

        if not available.empty:
            choices = {
                f'{row["id"]} - {row["title"]}': int(row["id"])
                for _, row in available.iterrows()
            }

            selected = st.selectbox(
                "Article vendu",
                list(choices.keys())
            )

            sale_price = st.number_input(
                "Prix de vente réel (€)",
                min_value=0.0,
                value=0.0,
                step=1.0
            )

            sale_fees = st.number_input(
                "Frais de vente (€)",
                min_value=0.0,
                value=0.0,
                step=0.5
            )

            other_costs = st.number_input(
                "Autres frais (€)",
                min_value=0.0,
                value=0.0,
                step=0.5
            )

            if st.button("Enregistrer la vente"):
                if sale_price <= 0:
                    st.error("Indique un prix de vente valide.")
                else:
                    update_sale(
                        choices[selected],
                        sale_price,
                        sale_fees,
                        other_costs
                    )
                    st.success("Vente enregistrée.")
                    st.rerun()

        st.divider()

        st.subheader("Supprimer un article")

        delete_id = st.number_input(
            "Identifiant de l'article à supprimer",
            min_value=0,
            step=1
        )

        if st.button("Supprimer définitivement"):
            if delete_id > 0:
                delete_deal(int(delete_id))
                st.success("Article supprimé.")
                st.rerun()

        st.download_button(
            "Exporter tout mon historique",
            history.to_csv(
                index=False, sep=";"
            ).encode("utf-8-sig"),
            "historique_vinted.csv",
            "text/csv"
        )


# =========================================================
# ONGLET 5 : STATISTIQUES
# =========================================================

with tab5:
    st.header("Statistiques de ton activité")

    history = load_deals()

    if history.empty:
        st.info("Les statistiques apparaîtront après tes premiers achats.")
    else:
        sold = history[history["status"] == "Vendu"].copy()

        total_articles = len(history)
        total_sold = len(sold)

        total_invested = (
            sold["purchase_price"]
            + sold["buyer_fees"]
            + sold["inbound_shipping"]
            + sold["packaging"]
        ).sum()

        total_revenue = sold["sale_price"].sum()

        total_fees = (
            sold["sale_fees"] + sold["other_costs"]
        ).sum()

        real_profit = total_revenue - total_invested - total_fees

        c1, c2, c3 = st.columns(3)

        c1.metric("Articles enregistrés", total_articles)
        c2.metric("Articles vendus", total_sold)
        c3.metric("Bénéfice réalisé", f"{real_profit:.2f} €")

        st.divider()

        if total_sold:
            st.metric(
                "Prix moyen de revente",
                f"{sold['sale_price'].mean():.2f} €"
            )

            st.metric(
                "Bénéfice moyen par vente",
                f"{real_profit / total_sold:.2f} €"
            )

            category_stats = sold.groupby("category").agg(
                ventes=("id", "count"),
                chiffre_affaires=("sale_price", "sum")
            ).reset_index()

            st.subheader("Catégories les plus vendues")
            st.dataframe(
                category_stats.sort_values(
                    "ventes", ascending=False
                ),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info(
                "Enregistre tes premières ventes pour obtenir "
                "des statistiques réelles."
            )


# =========================================================
# PIED DE PAGE
# =========================================================

st.divider()

st.caption(
    "Vinted Deal Finder V2 — Outil personnel d'analyse. "
    "Les estimations ne garantissent ni la vente ni le bénéfice. "
    "Vérifie les annonces, les photos, l'authenticité et les frais "
    "avant chaque achat."
)

