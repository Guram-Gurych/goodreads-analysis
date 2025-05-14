import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import streamlit as st

st.set_page_config(page_title="Goodreads Dashboard", layout="wide")


@st.cache_data
def load_data():
    df = pd.read_csv("../data/db.csv")
    df["genres_list"] = df["genres"].apply(
        lambda x: [g.strip() for g in str(x).split(",")]
    )
    df["n_genres"] = df["genres_list"].apply(len)
    return df


df = load_data()

st.sidebar.title("Навигация")
page = st.sidebar.radio(
    "Выберите раздел:", ["Главная", "Данные", "EDA", "Тренды", "Выводы"]
)

if page == "Главная":
    st.title("Goodreads: Анализ жанров, авторов и рейтингов")
    st.markdown(
        """
    Исследование построено на датасете книг с платформы Goodreads.
    Мы анализируем зависимости между жанрами, объёмом и рейтингами книг, выявляем топ авторов и делаем визуальные выводы.
    """
    )

elif page == "Данные":
    st.header("Общая таблица")
    st.dataframe(df)

    st.subheader("Счётчики")
    col1, col2, col3 = st.columns(3)
    col1.metric("Кол-во книг", len(df))
    col2.metric("Пропусков", df.isnull().sum().sum())
    col3.metric("Среднее число жанров", f"{df['n_genres'].mean():.2f}")

    st.subheader("Распределение жанров по книгам")
    genre_counts = {}
    for genre_list in df["genres_list"]:
        for g in genre_list:
            genre_counts[g] = genre_counts.get(g, 0) + 1
    genre_df = (
        pd.DataFrame.from_dict(genre_counts, orient="index", columns=["count"])
        .sort_values(by="count", ascending=False)
        .head(15)
    )
    fig, ax = plt.subplots()
    sns.barplot(x=genre_df["count"], y=genre_df.index, ax=ax)
    ax.set_xlabel("Число книг")
    ax.set_title("Топ-15 жанров")
    st.pyplot(fig)

elif page == "EDA":
    st.header("Первичный анализ")
    st.subheader("Распределение рейтингов")
    fig, ax = plt.subplots()
    sns.histplot(df["rating"], bins=20, kde=True, ax=ax)
    st.pyplot(fig)

    st.subheader("Распределение количества страниц")
    fig, ax = plt.subplots()
    sns.histplot(df["pages"].dropna(), bins=20, ax=ax)
    st.pyplot(fig)

elif page == "Тренды":
    st.header("Тренды и закономерности")

    st.subheader("Корреляционная матрица")
    corr_df = df[["rating", "pages", "ratings_count", "n_genres"]].corr()
    fig, ax = plt.subplots()
    sns.heatmap(corr_df, annot=True, cmap="coolwarm", fmt=".2f", ax=ax)
    st.pyplot(fig)

    st.subheader("Топ авторов по среднему рейтингу (≥ 3 книги)")
    author_stats = (
        df.groupby("author")
        .agg(n_books=("title", "count"), avg_rating=("rating", "mean"))
        .query("n_books >= 3")
        .sort_values("avg_rating", ascending=False)
        .head(15)
    )
    st.bar_chart(author_stats["avg_rating"])

elif page == "Выводы":
    st.header("Выводы и рекомендации")

    st.markdown(
        """
    - Жанры с наивысшим рейтингом — это преимущественно узкоспециализированные категории,
    которые читают вовлечённые аудитории.
    - Популярные жанры представлены шире, но имеют умеренные оценки.
    - Самые высокие средние рейтинги у авторов: J.K. Rowling, Tolkien, Rothfuss.
    - Корреляция между числом страниц и рейтингом положительная, но слабая.
    - Количество жанров у всех книг одинаково, и этот признак не несёт аналитической ценности.

    В будущем полезно расширить анализ за счёт годовых трендов.
    """
    )
