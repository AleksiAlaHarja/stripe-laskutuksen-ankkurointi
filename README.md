# Stripe Laskutuksen Ankkurointi (v0.9)

Komentorivityökalu Stripe-tilausten (Subscriptions) vuosittaiseen syklin ankkurointiin ja hallintaan. Työkalu mahdollistaa kesken vuoden liittyneiden jäsenten toistuvan laskutussyklin synkronoimisen tiettyyn kalenteripäivämäärään (esim. 1. tammikuuta).

## Ominaisuudet (v0.9)
- Tilausten tarkastelu: Listaa aktiiviset tilaukset, jäsenten nimet, tilaustunnukset ja seuraavat ankkurointipäivät hierarkkisesti lajiteltuna.
- Poikkeavien tunnistus: Erottelee tilaukset, jotka ovat jo tavoitepäivässä, sekä ne, joiden sykli on poikkeava.
- Ankkurointi: Päivittää poikkeavat tilaukset puhtaasti halutulle tulevalle ankkurointipäivämäärälle ilman ylimääräisiä väliaikalaskuja tai hyvityksiä (proration_behavior="none").
- Konfiguraatiohallinta: Tallentaa asetukset selkeään config.yaml-tiedostoon.

> **Huomio:** Nykyinen ankkurointilogiikka tukee alle 1 vuoden (<1v) aikajänteen siirtoja (esim. loppuvuodesta seuraavan vuoden alkuun). Yli vuoden päähän ulottuvat siirrot eivät toimi vielä luotettavasti tässä versiossa.

## Mistä saan Stripe API -avaimen?
1. Kirjaudu Stripe Dashboardiin osoitteessa: https://dashboard.stripe.com/apikeys
2. Suositus on luoda rajoitettu avain (**Restricted Key**), jolla on vain tarvittavat vähimmäisoikeudet:
   - **Customers:** Read
   - **Subscriptions:** Write
3. Vaihtoehtoisesti voit käyttää kehitysvaiheessa testitilan salaista avainta (alkaa `sk_test_`).

## Pika-asennus ja käynnistys (Copy-Paste)
Vaatimukset: Git pitää ilmeisesti olla asennettuna.

Kopioi ja liitä koko alla oleva lohko kerralla terminaaliin:

Asenna komennolla:
```bash
git clone https://github.com/AleksiAlaHarja/stripe-laskutuksen-ankkurointi.git # Ladataan tiedostot
cd stripe-laskutuksen-ankkurointi # Siirrytään kansioon
python3 -m venv venv # Luodaan virtuaaliympäristö ettei paketit mene sekaisin muiden projektien kanssa
source venv/bin/activate # Aktivoidaan äsken luotu virtuaaliympäristö
pip install --upgrade pip # Asennetaan pakettienhallinta
pip install stripe pyyaml # Asennetaan tarvittavat paketit
cp config.yaml.example config.yaml # Luodaan esimerkkitiedoston pohjalta oikea config.yaml -tiedosto
```
Käynnistä komennolla:
```bash
python3 stripe-laskutuksen-ankkurointi.py # Käynnistetään softa
```

Ohjelman käynnistyttyä aseta API-avain suoraan valikon kohdasta 1 tai muokkaa luotua `config.yaml`-tiedostoa.
