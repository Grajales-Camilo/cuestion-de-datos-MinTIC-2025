import '../styles/globals.css'
import Head from 'next/head' // Importar Head
// import Header from '../components/Header'
// import Footer from '../components/Footer'
// Importamos estilos de KaTeX para renderizar fórmulas matemáticas
import 'katex/dist/katex.min.css'

function MyApp({ Component, pageProps }) {
  return (
    <>
      <Head>
        <title>Cuestión de Datos</title>
        <meta name="description" content="Análisis de datos y políticas públicas en Colombia" />
        <link rel="icon" href="/images/favicon_io/favicon.ico" />
      </Head>
      {/* <Header /> */}
      <Component {...pageProps} />
      {/* <Footer /> */}
    </>
  )
}

export default MyApp
