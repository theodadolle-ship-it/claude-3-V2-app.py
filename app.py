import streamlit as st
import pandas as pd
import sqlite3
import statistics
import re
from datetime import datetime
from urllib.parse import quote_plus

# =====================================================
# CONFIGURATION
# =====================================================

APP_NAME = "Vinted Deal Finder V3"
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
    "Stone Island", "Tommy Hilfiger", "Sandro", "Maje",
    "Longchamp", "Michael Kors", "Lego", "Pokémon",
    "Nintendo Switch", "PlayStation", "Figurines",
    "Cartes Pokémon", "Vases", "Décoration vintage",
    "Lampes", "Objets design", "Montres", "Jeux de société",
    "Appareils photo", "Vinyles", "Consoles rétro"
]

DEFECT_WORDS = [
    "trou", "tache", "taché", "déchiré", "dechire",
    "défaut", "defaut", "usé", "use ", "bouloche",
    "décoloré", "decolore", "abîmé", "abime",
    "cassé", "casse", "fissure", "rayure",
    "manque une pièce", "incomplet", "à réparer",
    "a reparer", "ne fonctionne pas", "bloqué"
]

FAKE_WORDS = [
    "réplique", "replique", "contrefaçon",
    "contrefacon", "fake", "imitation", "copie"
]

CONDITIONS = [
    "Neuf avec étiquette",
    "Neuf sans étiquette",
    "Très bon état",
    "Bon état",
    "Satisfaisant",
    "Non précisé"
]


# =====================================================
# BASE DE DONNÉES
# =====================================================

def db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    with db() as conn:
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


def load_deals():
    with db() as conn:
        return pd.read_sql_query(
            "SELECT * FROM deals ORDER BY id DESC", conn
        )


def save_deal(data):
    with db() as conn:
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


def update_sale(deal_id, sale_price, fees, other):
    with db() as conn:
        conn.execute("""
        UPDATE deals
        SET status='Vendu', sale_price=?,
            sale_fees=?, other_costs=?
        WHERE id=?
        """, (sale_price, fees, other, deal_id))
        conn.commit()


def delete_deal(deal_id):
    with db() as conn:
        conn.execute("DELETE FROM deals WHERE id=?", (deal_id,))
        conn.commit()


# =====================================================
# ANALYSE
# =====================================================

def inspect_listing(description, condition):
    text = (description or "").lower()

    defects = [w for w in DEFECT_WORDS if w in text]
    suspicious = [w for w in FAKE_WORDS if w in text]

    if suspicious:
        return "À REJETER", defects, suspicious

    if defects:
        return "À VÉRIFIER", defects, suspicious

    if condition in ["Neuf avec étiquette", "Neuf sans étiquette",
                     "Très bon état"]:
        return "ÉTAT FAVORABLE À CONFIRMER", defects, suspicious

    return "À VÉRIFIER", defects, suspicious


def parse_prices(raw):
    values = []
    for item in raw.split(","):
        item = item.strip().replace("€", "").replace(",", ".")
        if item:
            try:
                value = float(item)
                if value > 0:
                    values.append(value)
            except ValueError:
                pass
    return values


def estimate_resale(prices, discount):
    if not prices:
        return None, "Aucune donnée"

    median = statistics.median(prices)
    estimate = median * discount

    if len(prices) >= 10:
        confidence = "Élevée"
    elif len(prices) >= 5:
        confidence = "Moyenne"
    else:
        confidence = "Faible"

    return round(estimate, 2), confidence


def calculate(purchase, buyer_fees, shipping, packaging,
              resale, sale_fees=0, other_costs=0):

    total_cost = (
        purchase + buyer_fees + shipping +
        packaging + sale_fees + other_costs
    )

    profit = resale - total_cost
    margin = profit / total_cost * 100 if total_cost else 0

    return round(profit, 2), round(margin, 1), round(total_cost, 2)


def max_purchase_price(resale, buyer_fees, shipping,
                       packaging, target_profit):

    return max(
        0,
        resale - buyer_fees - shipping - packaging - target_profit
    )


def make_vinted_url(search):
    return (
        "https://www.vinted.fr/catalog?search_text="
        + quote_plus(search)
        + "&order=newest_first"
    )


# =====================================================
# INTERFACE
# =====================================================

st.set_page_config(
    page_title=APP_NAME,
    page_icon="🔎",
    layout="wide"
)

init_db()

st.title("🔎 Vinted Deal Finder V3")
st.caption(
    "Exploration, analyse et suivi des opportunités d'achat-revente."
)

# PARAMÈTRES

with st.sidebar:
    st.header("⚙️ Paramètres")

    budget_max = st.number_input(
        "Budget maximum par article (€)",
        min_value=1.0,
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
        0.50, 1.00, 0.85, 0.05
    )

    st.caption(
        "Le coefficient réduit les prix comparables saisis. "
        "Il ne prouve pas qu'un article a réellement été vendu à ce prix."
    )


tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔍 Recherche",
    "➕ Ajouter une annonce",
    "📊 Opportunités",
    "📦 Historique",
    "📈 Statistiques"
])


# =====================================================
# 1. RECHERCHE ET EXPLORATION
# =====================================================

with tab1:

    st.header("Explorer toutes les catégories")

    st.write(
        "Choisis une catégorie ou un produit populaire "
        "pour ouvrir directement une recherche Vinted."
    )

    category = st.selectbox(
        "Catégorie à explorer",
        CATEGORIES
    )

    custom_category_search = st.text_input(
        "Préciser un type d'article",
        placeholder="Exemple : sac à main vintage"
    )

    search_category = custom_category_search.strip() or category

    st.link_button(
        "🔎 Rechercher cette catégorie sur Vinted",
        make_vinted_url(search_category)
    )

    st.divider()

    st.header("🔥 Produits populaires à surveiller")

    selected_products = st.multiselect(
        "Sélectionner les produits",
        POPULAR_PRODUCTS,
        default=POPULAR_PRODUCTS[:10]
    )

    custom_product = st.text_input(
        "Ajouter une marque ou un produit"
    )

    if st.button("Générer mes recherches populaires"):
        searches = selected_products.copy()

        if custom_product.strip():
            searches.append(custom_product.strip())

        st.session_state["searches"] = searches

    if "searches" in st.session_state:
        st.subheader("Tes recherches")

        for product in st.session_state["searches"]:
            st.markdown(
                f"- **{product}** — "
                f"[Voir les annonces récentes sur Vinted]"
                f"({make_vinted_url(product)})"
            )

    st.divider()

    st.info(
        "Les liens ouvrent les recherches Vinted, triées par nouveautés. "
        "Cette version ne récupère pas automatiquement les annonces "
        "du site. Il faut une source de données autorisée pour cela."
    )


# =====================================================
# 2. AJOUTER UNE ANNONCE
# =====================================================

with tab2:

    st.header("Analyser une annonce")

    st.caption(
        "Copie les informations de l'annonce Vinted. "
        "Tu peux aussi ajouter une photo pour la consulter ici."
    )

    with st.form("listing_form"):

        title = st.text_input("Titre de l'article")
        category = st.selectbox("Catégorie", CATEGORIES)
        brand = st.text_input("Marque")
        size = st.text_input("Taille / modèle")

        condition = st.selectbox(
            "État annoncé",
            CONDITIONS
        )

        description = st.text_area(
            "Description de l'annonce",
            height=120
        )

        url = st.text_input("Lien Vinted")

        photos = st.file_uploader(
            "Photos de l'annonce (facultatif)",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True
        )

        st.subheader("Prix d'achat")

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
            "Livraison (€)",
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

        st.subheader("Comparaison des prix")

        comparable_text = st.text_input(
            "Prix comparables séparés par des virgules",
            placeholder="30, 35, 39, 42"
        )

        evidence = st.selectbox(
            "Origine des prix comparables",
            [
                "Prix affichés d'annonces actives",
                "Annonces marquées vendues",
                "Ventes réellement observées",
                "Estimation personnelle",
                "Aucune preuve"
            ]
        )

        notes = st.text_area("Notes personnelles")

        submitted = st.form_submit_button(
            "Analyser et enregistrer",
            type="primary"
        )

    if photos:
        st.subheader("Photos importées")
        cols = st.columns(3)

        for i, photo in enumerate(photos):
            with cols[i % 3]:
                st.image(photo, use_container_width=True)

        st.warning(
            "Les photos sont affichées pour inspection manuelle. "
            "Cette version ne réalise pas encore d'analyse visuelle automatique."
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
            result, defects, suspicious = inspect_listing(
                description, condition
            )

            prices = parse_prices(comparable_text)

            resale, confidence = estimate_resale(
                prices, discount
            )

            st.subheader("Résultat de l'analyse")

            if suspicious:
                st.error(
                    "Risque de contrefaçon : "
                    + ", ".join(suspicious)
                )

            elif defects:
                st.warning(
                    "Défauts mentionnés dans la description : "
                    + ", ".join(defects)
                )

            else:
                st.info(
                    "Aucun défaut repéré dans le texte. "
                    "Cela ne garantit pas l'état réel de l'article."
                )

            if resale is None:
                st.warning(
                    "Ajoute des prix comparables pour calculer "
                    "une estimation de revente."
                )
                resale_to_save = 0.0
                confidence = "Aucune donnée"

            else:
                profit, margin, total_cost = calculate(
                    purchase, buyer_fees, shipping,
                    packaging, resale
                )

                max_price = max_purchase_price(
                    resale, buyer_fees, shipping,
                    packaging, min_profit
                )

                st.metric("Revente estimée", f"{resale:.2f} €")
                st.metric("Bénéfice estimé", f"{profit:.2f} €")
                st.metric("Marge estimée", f"{margin:.1f} %")

                st.metric(
                    "Prix d'achat maximal conseillé",
                    f"{max_price:.2f} €"
                )

                st.write(f"Comparables utilisés : {len(prices)}")
                st.write(f"Confiance : {confidence}")
                st.write(f"Résultat de l'état : {result}")

                if evidence == "Prix affichés d'annonces actives":
                    st.warning(
                        "Les prix affichés ne sont pas des prix de vente réels."
                    )

                if result == "À REJETER":
                    st.error(
                        "Attention : annonce à écarter en raison "
                        "des termes suspects."
                    )

                resale_to_save = resale

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
                "resale": resale_to_save,
                "evidence": evidence,
                "confidence": confidence,
                "url": url,
                "status": "À étudier",
                "notes": notes
            })

            st.success("Annonce enregistrée dans ton historique.")


# =====================================================
# 3. OPPORTUNITÉS
# =====================================================

with tab3:

    st.header("Mes meilleures opportunités")

    deals = load_deals()

    if deals.empty:
        st.info("Ajoute tes premières annonces pour les retrouver ici.")

    else:
        opportunities = deals.copy()

        opportunities["cout_total"] = (
            opportunities["purchase_price"]
            + opportunities["buyer_fees"]
            + opportunities["inbound_shipping"]
            + opportunities["packaging"]
        )

        opportunities["benefice_estime"] = (
            opportunities["resale_estimate"]
            - opportunities["cout_total"]
        )

        opportunities["marge_estimee"] = (
            opportunities["benefice_estime"] /
            opportunities["cout_total"].replace(0, pd.NA)
        ) * 100

        opportunities = opportunities[
            (opportunities["status"] != "Vendu")
            & (opportunities["purchase_price"] <= budget_max)
            & (opportunities["benefice_estime"] >= min_profit)
            & (opportunities["marge_estimee"] >= min_margin)
            & (opportunities["resale_estimate"] > 0)
        ]

        opportunities = opportunities.sort_values(
            "benefice_estime", ascending=False
        )

        st.metric(
            "Opportunités correspondant à tes critères",
            len(opportunities)
        )

        if not opportunities.empty:

            st.dataframe(
                opportunities[[
                    "title", "category", "brand",
                    "purchase_price", "resale_estimate",
                    "benefice_estime", "marge_estimee",
                    "confidence", "url"
                ]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "url": st.column_config.LinkColumn(
                        "Annonce",
                        display_text="Ouvrir"
                    )
                }
            )

        else:
            st.info(
                "Aucune opportunité ne correspond actuellement "
                "à tes paramètres."
            )


# =====================================================
# 4. HISTORIQUE
# =====================================================

with tab4:

    st.header("Historique des articles")

    history = load_deals()

    if history.empty:
        st.info("Ton historique est vide.")

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

        delete_id = st.number_input(
            "Identifiant à supprimer",
            min_value=0,
            step=1
        )

        if st.button("Supprimer cet article"):
            if delete_id > 0:
                delete_deal(int(delete_id))
                st.success("Article supprimé.")
                st.rerun()

        st.download_button(
            "Exporter mon historique CSV",
            history.to_csv(
                index=False, sep=";"
            ).encode("utf-8-sig"),
            "historique_vinted.csv",
            "text/csv"
        )


# =====================================================
# 5. STATISTIQUES
# =====================================================

with tab5:

    st.header("Statistiques")

    history = load_deals()

    if history.empty:
        st.info("Les statistiques apparaîtront avec tes premiers articles.")

    else:

        sold = history[
            history["status"] == "Vendu"
        ].copy()

        total_articles = len(history)
        total_sold = len(sold)

        invested = (
            sold["purchase_price"]
            + sold["buyer_fees"]
            + sold["inbound_shipping"]
            + sold["packaging"]
        ).sum()

        revenue = sold["sale_price"].sum()

        fees = (
            sold["sale_fees"] + sold["other_costs"]
        ).sum()

        profit = revenue - invested - fees

        c1, c2, c3 = st.columns(3)

        c1.metric("Articles suivis", total_articles)
        c2.metric("Articles vendus", total_sold)
        c3.metric("Bénéfice réalisé", f"{profit:.2f} €")

        if total_sold:

            st.metric(
                "Prix moyen de vente",
                f"{sold['sale_price'].mean():.2f} €"
            )

            st.metric(
                "Bénéfice moyen par vente",
                f"{profit / total_sold:.2f} €"
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


# =====================================================
# PIED DE PAGE
# =====================================================

st.divider()

st.caption(
    "Vinted Deal Finder V3 — Outil personnel d'analyse. "
    "Les estimations ne garantissent ni la vente ni le bénéfice. "
    "Vérifie les annonces, les photos, l'authenticité et les frais "
    "avant chaque achat."
)