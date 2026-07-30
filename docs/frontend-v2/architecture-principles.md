Elogios para Fundamentos de Arquitectura de Software

Mark y Neal lo han hecho de nuevo: esta segunda edición revisada
y ampliada de su éxito de ventas es un recurso indispensable para
explorar la arquitectura de software moderna a través de una
lente contemporánea. Con una comprensión matizada de lo que
realmente implica la arquitectura de software, esta guía
exhaustiva comienza con la importancia crítica del análisis de
compensaciones, para luego profundizar en una amplia gama de
estilos arquitectónicos y las filosofías que los sustentan, junto con
exámenes detallados de las topologías de datos y de equipos. Ya
sea que seas un arquitecto "accidental" que asume el rol o un
veterano experimentado que busca refinar sus habilidades, este
libro ofrece las herramientas y el conocimiento que necesitas para
sobresalir en tu oficio.

—Raju Gandhi, autor de Head First Git y coautor de
Head First Software Architecture

Neal y Mark no solo son arquitectos de software sobresalientes;
también son maestros excepcionales. Con Fundamentos de
Arquitectura de Software, han logrado condensar el extenso tema
de la arquitectura en una obra concisa que refleja sus décadas de
experiencia. Ya sea que seas nuevo en el rol o hayas sido un
arquitecto en ejercicio durante muchos años, la edición
actualizada de este libro te ayudará a ser mejor en tu trabajo.
Ojalá lo hubieran escrito antes en mi carrera. Ahora he utilizado
ambas ediciones con mis estudiantes de posgrado en arquitectura,
y seguiré recomendándolo ampliamente en esta forma ampliada.
—Nathaniel Schutta, coautor de Fundamentals of
Software Engineering

1Mark y Neal se propusieron alcanzar una meta formidable —
dilucidar los muchos y estratificados fundamentos necesarios para
sobresalir en la arquitectura de software— y una vez más han
completado su misión. El campo de la arquitectura de software
evoluciona continuamente, y el rol requiere una amplitud y
profundidad desalentadoras de conocimientos y habilidades. Este
libro actualizado servirá como guía para muchos mientras navegan
en su viaje hacia el dominio de la arquitectura de software.

—Rebecca J. Parsons, asesora tecnológica y antigua
CTO/CTO emérita de Thoughtworks

Mark y Neal capturan verdaderamente consejos del mundo real
para que los tecnólogos impulsen la excelencia en la arquitectura.
Logran esto identificando las características comunes de la
arquitectura y las compensaciones que son necesarias para
impulsar el éxito.

—Cassie Shum, directora técnica, Thoughtworks

2Fundamentos de Arquitectura
de Software

SEGUNDA EDICIÓN

Un enfoque de ingeniería moderno

Mark Richards y Neal Ford

3Fundamentos de Arquitectura de Software

por Mark Richards y Neal Ford

Copyright © 2025 Mark Richards y Neal Ford. Todos los derechos
reservados.

Impreso en los Estados Unidos de América.

Publicado por O’Reilly Media, Inc., 1005 Gravenstein Highway North,
Sebastopol, CA 95472.

Los libros de O’Reilly pueden comprarse para uso educativo,
empresarial o promocional. También hay ediciones en línea
disponibles para la mayoría de los títulos (http://oreilly.com). Para
obtener más información, ponte en contacto con nuestro
departamento de ventas corporativas/institucionales: 800-998-9938
o corporate@oreilly.com.

Editora de adquisiciones: Louise Corrigan

Editora de desarrollo: Sarah Grey

Editor de producción: Christopher Faucher

Correctora de estilo: Sonia Saruba

Corrector de pruebas: Piper Content Partners

Indexador: WordCo Indexing Services, Inc.

Diseñador de interiores: David Futato

Diseñadora de portada: Karen Montgomery

Ilustradora: Kate Dullea

Enero de 2020: Primera edición

4Marzo de 2025: Segunda edición

Historial de revisiones para la segunda edición

12-03-2025: Primer lanzamiento

Consulta http://oreilly.com/catalog/errata.csp?isbn=9781098175511
para ver los detalles del lanzamiento.

El logotipo de O’Reilly es una marca comercial registrada de O’Reilly
Media, Inc. Fundamentos de Arquitectura de Software, la imagen de
la portada y la imagen comercial relacionada son marcas comerciales
de O’Reilly Media, Inc.

Las opiniones expresadas en esta obra son las de los autores y no
representan las opiniones de la editorial. Si bien la editorial y los
autores han realizado esfuerzos de buena fe para asegurar que la
información y las instrucciones contenidas en esta obra sean
precisas, la editorial y los autores renuncian a toda responsabilidad
por errores u omisiones, incluyendo, sin limitación, la
responsabilidad por daños resultantes del uso o la confianza en esta
obra. El uso de la información y las instrucciones contenidas en esta
obra es bajo tu propio riesgo. Si algún ejemplo de código u otra
tecnología que esta obra contenga o describa está sujeto a licencias
de código abierto o a los derechos de propiedad intelectual de otros,
es tu responsabilidad asegurarte de que su uso cumpla con dichas
licencias y/o derechos.

978-1-098-17551-1

[LSI]

5Prefacio

Prefacio de la segunda edición

“¡Vaya, hay mucho ahí!”

Cuando nos propusimos escribir la segunda edición de Fundamentos
de Arquitectura de Software, teníamos algunas ideas sobre cosas
que queríamos desarrollar y mejorar de la primera edición, pero al
igual que muchos proyectos de software, siguió creciendo.

Uno de nuestros objetivos cumplidos fue hacer que las secciones de
estilos fueran más consistentes, volviéndolas más útiles para las
comparaciones. También hicimos algunos cambios en nuestras
calificaciones de estrellas para añadir secciones y algunas categorías
nuevas, y agregamos nuevas secciones sobre consideraciones de la
nube, topologías de datos, topologías de equipo y gobernanza para
cada estilo arquitectónico. En el camino, realizamos adiciones
importantes a varios capítulos sobre temas populares, como los
capítulos 15 y 18, y añadimos un capítulo nuevo (Capítulo 11) sobre
el estilo arquitectónico de monolito modular.

También añadimos varios capítulos completamente nuevos que
cubren patrones arquitectónicos en el Capítulo 20, las intersecciones
de la arquitectura en el Capítulo 26, y una revisión de nuestras leyes
de arquitectura de software (de las cuales hay un nuevo corolario y
una nueva ley) en el Capítulo 27.

Prefacio de la primera edición

Axioma

Una declaración o proposición que se considera establecida,
aceptada o evidentemente verdadera.

6Los matemáticos crean teorías basadas en axiomas: suposiciones de
cosas indiscutiblemente verdaderas. Los arquitectos de software
también construyen teorías sobre axiomas, pero el mundo del
software es, bueno, más blando que las matemáticas: las cosas
fundamentales siguen cambiando a un ritmo acelerado, incluidos los
axiomas en los que basamos nuestras teorías.

El ecosistema del desarrollo de software existe en un estado
constante de equilibrio dinámico: aunque se encuentra en un estado
equilibrado en cualquier momento dado, exhibe un comportamiento
dinámico a largo plazo. Un gran ejemplo moderno de la naturaleza
de este ecosistema sigue al ascenso de la contenedorización y los
cambios que la acompañan: herramientas como Kubernetes no
existían hace una década, y sin embargo ahora existen conferencias
de software enteras para atender a sus usuarios. El ecosistema del
software cambia de forma caótica: un pequeño cambio provoca otro
pequeño cambio; cuando se repite cientos de veces, genera un
nuevo ecosistema.

Los arquitectos tienen la importante responsabilidad de cuestionar
las suposiciones y los axiomas que quedan de eras anteriores.
Muchos de los libros sobre arquitectura de software fueron escritos
en una era que apenas se parece al mundo actual. De hecho, los
autores creemos que debemos cuestionar los axiomas
fundamentales de forma regular, a la luz de las mejores prácticas de
ingeniería, los ecosistemas operativos, los procesos de desarrollo de
software... todo lo que conforma el desordenado y dinámico
equilibrio donde los arquitectos y desarrolladores trabajan cada día.

Los observadores atentos de la arquitectura de software han sido
testigos a lo largo del tiempo de una evolución de las capacidades.
Comenzando con las prácticas de ingeniería de Extreme
Programming (Programación Extrema), continuando con la entrega
continua, la revolución de DevOps, los microservicios, la
contenedorización y ahora los recursos basados en la nube, todas
estas innovaciones llevaron a nuevas capacidades y

7compensaciones. A medida que las capacidades cambiaron, también
lo hicieron las perspectivas de los arquitectos sobre la industria.
Durante muchos años, la definición irónica de arquitectura de
software era "las cosas que son difíciles de cambiar más adelante".
Más tarde, apareció el estilo de arquitectura de microservicios,
donde el cambio es una consideración de diseño de primer nivel.

Cada nueva era requiere nuevas prácticas, herramientas,
mediciones, patrones y una serie de otros cambios. Este libro analiza
la arquitectura de software bajo una luz moderna, teniendo en
cuenta todas las innovaciones de la última década, junto con
algunas métricas y medidas nuevas adecuadas para las nuevas
estructuras y perspectivas actuales.

El subtítulo de nuestro libro es "Un enfoque de ingeniería moderno".
Durante mucho tiempo, los desarrolladores han deseado cambiar el
desarrollo de software de un oficio, donde artesanos calificados
pueden crear obras únicas, a una disciplina de ingeniería, lo que
implica repetibilidad, rigor y análisis efectivo. Si bien la ingeniería de
software todavía está por detrás de otros tipos de disciplinas de
ingeniería por muchos órdenes de magnitud (para ser justos, el
software es una disciplina muy joven en comparación con la mayoría
de los otros tipos de ingeniería), los arquitectos han logrado grandes
mejoras, las cuales discutiremos. En particular, las prácticas
modernas de ingeniería Ágil han permitido grandes avances en los
tipos de sistemas que los arquitectos diseñan.

También abordamos el tema críticamente importante del análisis de
compensaciones. Como desarrollador de software, es fácil
enamorarse de una tecnología o enfoque en particular. Pero los
arquitectos siempre deben evaluar con sobriedad lo bueno, lo malo y
lo feo de cada elección, y prácticamente nada en el mundo real
ofrece opciones binarias convenientes; todo es una compensación.
Dada esta perspectiva pragmática, nos esforzamos por eliminar los
juicios de valor sobre la tecnología y, en su lugar, nos enfocamos en

8analizar las compensaciones para equipar a nuestros lectores con
una mirada analítica hacia las elecciones tecnológicas.

Este libro no convertirá a nadie en arquitecto de software de la
noche a la mañana; es un campo matizado con muchas facetas.
Queremos ofrecer a los arquitectos actuales y futuros una buena
visión general moderna de la arquitectura de software y sus
múltiples aspectos, desde la estructura hasta las habilidades
blandas. Aunque este libro cubre patrones conocidos, adoptamos un
nuevo enfoque, apoyándonos en las lecciones aprendidas, las
herramientas, las prácticas de ingeniería y otros aportes. Tomamos
muchos axiomas existentes en la arquitectura de software y los
replanteamos a la luz del ecosistema actual, y diseñamos
arquitecturas teniendo en cuenta el panorama moderno.

Convenciones utilizadas en este libro

En este libro se utilizan las siguientes convenciones tipográficas:

Cursiva

Indica términos nuevos, URLs, direcciones de correo
electrónico, nombres de archivos y extensiones de archivos.

Ancho constante

Se utiliza para listados de programas, así como dentro de los
párrafos para referirse a elementos del programa como
nombres de variables o funciones, bases de datos, tipos de
datos, variables de entorno, sentencias y palabras clave.

Este elemento significa un consejo o sugerencia.

CONSEJO

9Este elemento significa una nota general.

NOTA

ADVERTENCIA

Este elemento indica una advertencia o precaución.

Material complementario

Visita http://fundamentalsofsoftwarearchitecture.com para acceder a
los recursos complementarios de este libro.

Si tienes una pregunta técnica o un problema al usar los ejemplos de
código, envía un correo electrónico a bookquestions@oreilly.com.

Este libro está aquí para ayudarte a hacer tu trabajo. En general, si
se ofrece código de ejemplo con este libro, puedes usarlo en tus
programas y documentación. No necesitas contactarnos para pedir
permiso a menos que estés reproduciendo una parte significativa del
código. Por ejemplo, escribir un programa que utilice varios
fragmentos de código de este libro no requiere permiso. Vender o
distribuir ejemplos de los libros de O’Reilly sí requiere permiso.
Responder a una pregunta citando este libro y mencionando código
de ejemplo no requiere permiso. Incorporar una cantidad
significativa de código de ejemplo de este libro en la documentación
de tu producto sí requiere permiso.

Agradecemos, pero generalmente no requerimos, la atribución. Una
atribución suele incluir el título, el autor, la editorial y el ISBN. Por
ejemplo: “Fundamentos de Arquitectura de Software, Segunda
Edición, de Mark Richards y Neal Ford (O’Reilly). Copyright 2025
Mark Richards y Neal Ford, 978-1-098-17551-1.”

10Si sientes que el uso que haces de los ejemplos de código cae fuera
del uso justo o del permiso otorgado anteriormente, no dudes en
contactarnos en permissions@oreilly.com.

O’Reilly Online Learning

NOTA

Durante más de 40 años, O’Reilly Media ha proporcionado capacitación
en tecnología y negocios, conocimiento e información para ayudar a las
empresas a tener éxito.

Nuestra red única de expertos e innovadores comparte su
conocimiento y experiencia a través de libros, artículos y nuestra
plataforma de aprendizaje en línea. La plataforma de aprendizaje en
línea de O’Reilly te brinda acceso bajo demanda a cursos de
capacitación en vivo, rutas de aprendizaje detalladas, entornos de
programación interactivos y una vasta colección de texto y video de
O’Reilly y de más de 200 editoriales adicionales. Para más
información, por favor visita http://oreilly.com.

Cómo contactarnos

Por favor, dirige tus comentarios y preguntas sobre este libro a la
editorial:

O’Reilly Media, Inc.

1005 Gravenstein Highway North

Sebastopol, CA 95472

800-889-8969 (en los Estados Unidos o Canadá)

11707-827-7019 (internacional o local)

707-829-0104 (fax)

support@oreilly.com

https://oreilly.com/about/contact.html

Tenemos una página web para este libro, donde enumeramos las
erratas, los ejemplos y cualquier información adicional. Puedes
acceder a esta página en https://oreil.ly/fundamentals-of-software-
architecture-2e.

Para noticias e información sobre nuestros libros y cursos, visita
https://oreilly.com.

Encuéntranos en LinkedIn: https://linkedin.com/company/oreilly-
media.

Míranos en YouTube: https://youtube.com/oreillymedia.

Agradecimientos

Mark y Neal queremos agradecer a todas las personas que asistieron
a nuestras clases, talleres, sesiones de conferencias y reuniones de
grupos de usuarios, así como a todas las personas que escucharon
versiones de este material y proporcionaron comentarios invaluables.
También nos gustaría agradecer al equipo editorial de O'Reilly,
quienes hicieron de esto una experiencia tan indolora como puede
ser escribir un libro. En particular, queremos agradecer a nuestras
editoras de la primera edición, Alicia Young y Virginia Wilson, y a
nuestra editora de la segunda edición, Sarah Grey.

12Agradecimientos de Mark Richards

Además de los agradecimientos anteriores, me gustaría dar las
gracias a mi encantadora esposa, Rebecca. Encargarte de todo lo
demás en casa y sacrificar la oportunidad de trabajar en tu propio
libro me permitió realizar trabajos de consultoría adicionales y hablar
en más conferencias y clases de capacitación, dándome la
oportunidad de practicar y perfeccionar el material de este libro.
Eres la mejor.

Agradecimientos de Neal Ford

Me gustaría agradecer a mi familia extendida, a Thoughtworks como
colectivo, y a Rebecca Parsons y Martin Fowler como partes
individuales del mismo. Thoughtworks es un grupo extraordinario de
personas que logran generar valor para los clientes mientras
mantienen un ojo atento a por qué funcionan las cosas para que
podamos mejorarlas. Thoughtworks apoyó este libro de muchas
maneras y continúa formando a Thoughtworkers que desafían e
inspiran cada día. También me gustaría agradecer a nuestro club de
cócteles del vecindario por ser un escape regular de la rutina. Por
último, me gustaría agradecer a mi esposa, Candy, cuya tolerancia
para cosas como escribir libros y hablar en conferencias
aparentemente no tiene límites. Durante décadas ella me ha
mantenido con los pies en la tierra y lo suficientemente cuerdo para
funcionar, y espero que lo siga haciendo por décadas más como el
amor de mi vida.


32Parte I. Fundamentos

Para entender los compromisos importantes en la arquitectura, los
desarrolladores deben comprender algunos conceptos básicos y la
terminología relacionada con los componentes, la modularidad, el
acoplamiento y la conasciencia (connascence).

33Capítulo 2. Pensamiento
arquitectónico

El pensamiento arquitectónico consiste en ver las cosas con el ojo de
un arquitecto; en otras palabras, desde un punto de vista
arquitectónico. Comprender cómo un cambio particular podría
impactar la escalabilidad general, prestar atención a cómo
interactúan las diferentes partes de un sistema y saber qué librerías
y frameworks de terceros serían más apropiados para una situación
determinada son ejemplos de pensar arquitectónicamente.

Ser capaz de pensar como un arquitecto implica, primero, entender
qué es la arquitectura de software y las diferencias entre
arquitectura y diseño. Luego, implica tener una gran amplitud de
conocimientos para ver soluciones y posibilidades que otros no ven;
comprender la importancia de los impulsores de negocio y cómo se
traducen en intereses arquitectónicos; y entender, analizar y conciliar
las compensaciones (trade-offs) entre diversas soluciones y
tecnologías.

En este capítulo, exploraremos estos aspectos de pensar como un
arquitecto.

Arquitectura frente a diseño

Tómate un momento e imagina la casa de tus sueños en tu mente.
¿Cuántos pisos tiene? ¿El techo es plano o inclinado? ¿Es una casa
estilo rancho, grande y de una sola planta, o una casa
contemporánea de varios pisos? ¿Cuántas recámaras tiene? Todas
estas cosas definen la estructura general de la casa; en otras
palabras, su arquitectura. Ahora tómate un momento para imaginar
el interior de la casa. ¿Tiene alfombras o suelos de madera? ¿De qué

34color son las paredes? ¿Hay lámparas de pie o luces que cuelgan del
techo? Todas estas cosas se relacionan con el diseño de la casa.

De manera similar, la arquitectura de software se trata menos de la
apariencia de un sistema y más de su estructura, mientras que el
diseño se trata más de la apariencia de un sistema y menos de su
estructura. Por ejemplo, la elección de usar microservicios define la
estructura y forma del sistema (su arquitectura), mientras que el
aspecto y la sensación de la pantalla de la interfaz de usuario (UI)
definen el diseño del sistema.

Pero ¿qué pasa con decisiones como separar un servicio en partes
más pequeñas o decidir un framework de interfaz de usuario?
Desafortunadamente, la mayoría de las decisiones de este tipo caen
en algún lugar de un espectro entre la arquitectura y el diseño, lo
que dificulta determinar qué debe considerarse arquitectura.

Aprovechar los siguientes criterios puede ayudar a determinar si algo
tiene más que ver con la arquitectura o con el diseño:

¿Es de naturaleza más estratégica o más táctica?

¿Cuánto esfuerzo requerirá cambiarlo o construirlo?

¿Qué tan significativas son las compensaciones (trade-offs)?

Estos factores se muestran en la Figura 2-1, que ilustra el espectro
entre arquitectura y diseño para ayudar a determinar dónde se sitúa
una decisión y quién debería tener la responsabilidad de la misma.

35Este gráfico presenta el espectro comparativo entre la arquitectura y el diseño de

software mediante tres criterios clave de evaluación. En el extremo izquierdo, que

define la arquitectura, se sitúan las decisiones de carácter estratégico que implican

un  gran  esfuerzo  de  implementación  o  cambio  y  conllevan  compensaciones

significativas.  Por  el  contrario,  hacia  el  extremo  derecho,  el  diseño  se  caracteriza

por  decisiones  tácticas  con  un  bajo  esfuerzo  asociado  y  compensaciones

insignificantes. Los puntos marcados de la A a la D ilustran esta transición gradual,

permitiéndote categorizar cualquier decisión técnica según su impacto estratégico,

la  dificultad  de  su  ejecución  y  la  relevancia  de  los  compromisos  asumidos.

(Accesibilidad de la imagen)

Figura 2-1. El espectro entre arquitectura y diseño

Decisiones estratégicas frente a tácticas

Cuanto más estratégica es una decisión, más arquitectónica se
vuelve. Por el contrario, cuanto más táctica es una decisión, más
probable es que se trate de diseño. Las decisiones estratégicas son
generalmente a largo plazo, mientras que las decisiones tácticas son
generalmente a corto plazo y suelen ser independientes de otras
acciones o decisiones.

Una buena forma de determinar si una decisión es más estratégica o
táctica es considerar las siguientes preguntas:

36¿Cuánto pensamiento y planificación conlleva la decisión?

Una decisión que toma un par de minutos es más probable
que sea táctica y, por lo tanto, más sobre diseño, mientras
que una decisión que requiere semanas de planiﬁcación es
probable que sea más estratégica y, por ende, más sobre
arquitectura.

¿Cuántas personas están involucradas en la decisión?

Una decisión tomada a solas o con un colega es
probablemente más táctica y está en el lado del diseño del
espectro, mientras que una decisión que requiere muchas
reuniones con muchos interesados (stakeholders) diferentes
es probablemente más estratégica y está en el lado
arquitectónico del espectro.

¿Es la decisión una visión a largo plazo o una acción a corto plazo?

Una decisión que es probable que cambie pronto suele ser
de naturaleza táctica y se trataría más de diseño, mientras
que una que durará mucho tiempo suele ser más estratégica
y más sobre arquitectura.

Si bien estas preguntas son un poco subjetivas, ayudan de todos
modos a determinar si algo es estratégico o táctico y, por lo tanto,
más sobre arquitectura o diseño.

Nivel de esfuerzo

En su famoso artículo "¿Quién necesita un arquitecto?", el arquitecto
de software Martin Fowler escribe que la arquitectura es "las cosas
que son difíciles de cambiar". Cuanto más difícil es cambiar algo,
generalmente se requiere más esfuerzo, lo que sitúa esa decisión o
actividad hacia el lado arquitectónico del espectro. Por el contrario,

37algo que requiere un esfuerzo mínimo para implementarse o
cambiarse se sitúa más en el lado del diseño del espectro.

Por ejemplo, pasar de una arquitectura en capas monolítica a
microservicios requeriría un esfuerzo significativo, por lo que se
trataría más de arquitectura. Reorganizar los campos en una pantalla
requeriría un esfuerzo mínimo y, por lo tanto, se trataría más de
diseño.

La importancia de las compensaciones (trade-
offs)

Analizar las compensaciones (trade-offs) de una decisión particular
puede ayudar mucho a determinar si se trata más de arquitectura o
de diseño. Cuanto más significativas sean las compensaciones, más
arquitectónica tiende a ser la decisión. Por ejemplo, elegir usar el
estilo de arquitectura de microservicios proporciona mejor
escalabilidad, agilidad, elasticidad y tolerancia a fallos. Sin embargo,
esta arquitectura es muy compleja, muy costosa, tiene una
consistencia de datos deficiente y no rinde bien debido al
acoplamiento de servicios. Estas son compensaciones bastante
significativas. Podemos concluir que esta decisión está más del lado
arquitectónico del espectro que del diseño.

Incluso las decisiones de diseño tienen compensaciones. Por
ejemplo, separar un archivo de clase proporciona mejor
mantenibilidad y legibilidad, a costa de gestionar más clases. Estas
compensaciones no son excesivamente significativas (especialmente
comparadas con las de los microservicios), por lo que esta decisión
está más del lado del diseño del espectro.

Amplitud técnica

A diferencia de los desarrolladores, quienes deben tener una
cantidad significativa de profundidad técnica para realizar su trabajo,

38los arquitectos de software deben tener una cantidad significativa de
amplitud técnica para ver las cosas desde un punto de vista
arquitectónico. La profundidad técnica se trata de tener un
conocimiento profundo de un lenguaje de programación, plataforma,
framework o producto en particular, mientras que la amplitud técnica
se trata de saber un poco de muchas cosas.

Para entender mejor la diferencia, considera la pirámide del
conocimiento que se muestra en la Figura 2-2. Encapsula todo el
conocimiento técnico del mundo, que se puede desglosar en tres
niveles: cosas que sabes, cosas que sabes que no sabes y cosas que
no sabes que no sabes.

39Esta  imagen  presenta  una  pirámide  dividida  en  tres  secciones  horizontales  que

ilustran los niveles del conocimiento técnico. En la punta superior, de color verde

claro,  se  encuentra  lo  que  sabes;  en  la  franja  intermedia,  de  color  amarillo,  se

ubica  lo  que  sabes  que  no  sabes;  y  finalmente,  en  la  base  más  amplia  de  color

rojizo, se describe lo que no sabes que no sabes. (Accesibilidad de la imagen)

Figura 2-2. La pirámide que representa todo el conocimiento

Cosas que sabes incluye las tecnologías, frameworks, lenguajes y
herramientas que los tecnólogos usan a diario para realizar su
trabajo (como un programador de Java que sabe Java). Son buenos,
o incluso expertos, en todas estas cosas. Observa que este nivel de
conocimiento (representado por la parte superior de la pirámide) es
el más pequeño y contiene la menor cantidad de cosas. Esto se debe
a que la mayoría de los tecnólogos tienen que elegir las áreas en las
que desarrollar experiencia; nadie puede ser experto en todo.

40Cosas que sabes que no sabes (la parte media de la pirámide)
incluye cosas sobre las que un tecnólogo sabe un poco o ha oído
hablar, pero en las que tiene poca o ninguna experiencia o pericia.
Por ejemplo, la mayoría de los tecnólogos han oído hablar de Clojure
y saben que es un lenguaje de programación basado en Lisp, pero
no pueden escribir código fuente en Clojure. Este nivel de
conocimiento es mucho más grande que el nivel superior. Esto se
debe a que las personas pueden familiarizarse con muchas más
cosas de las que pueden especializarse.

Cosas que no sabes que no sabes es la parte más grande de la
pirámide del conocimiento. Incluye todo el conjunto de tecnologías,
herramientas, frameworks y lenguajes que serían la solución
perfecta a un problema, si tan solo el tecnólogo que intenta resolver
el problema supiera que estas soluciones existen. El objetivo en la
carrera de cualquier individuo debería ser mover las cosas de las
cosas que no sabes que no sabes a la segunda área de la pirámide,
las cosas que sabes que no sabes —y, cuando la pericia se vuelva
necesaria, mover las cosas de la parte media de la pirámide a la
cima: las cosas que sabes.

Al principio de la carrera de un desarrollador, expandir la cima de la
pirámide (Figura 2-3) significa ganar una valiosa pericia. Sin
embargo, las cosas que sabes también son cosas que debes
mantener; nada es estático en el mundo del software. Si un
desarrollador se vuelve experto en Ruby on Rails, esa pericia no
durará si ignora Ruby on Rails por un año o dos. Mantener las cosas
en la cima de la pirámide requiere una inversión de tiempo para
conservar la pericia. Esta parte superior representa la profundidad
técnica del individuo: las cosas que conoce muy bien.

41Esta ilustración presenta una pirámide de conocimiento segmentada en tres áreas

de  distintos  colores.  En  el  vértice  superior,  resaltado  en  verde  claro,  se  ubica  lo

que sabes, acompañado de una nota lateral en rojo que indica que estas son las

cosas  que  debes  mantener  para  no  perder  tu  pericia.  El  nivel  central,  de  color

amarillo, muestra lo que sabes que no sabes, mientras que la base más extensa,

en  color  rojizo,  representa  lo  que  no  sabes  que  no  sabes.  (Accesibilidad  de  la

imagen)

Figura 2-3. Los desarrolladores deben mantener su pericia para conservarla

Sin embargo, la naturaleza del conocimiento cambia a medida que
los desarrolladores transicionan al rol de arquitecto. Gran parte del
valor de un arquitecto es que tiene una comprensión amplia de la
tecnología y de cómo usarla para resolver problemas particulares.
Por ejemplo, es mejor para un arquitecto saber que existen cinco
soluciones para un problema determinado que tener una pericia
singular en solo una. Las partes más importantes de la pirámide

42para los arquitectos son las secciones superior y media; qué tanto
penetra la sección media en la sección inferior representa la
amplitud técnica de un arquitecto, como se muestra en la Figura 2-4.

Este  gráfico  ilustra  la  pirámide  del  conocimiento  técnico,  categorizando  la

experiencia  en  tres  niveles.  El  nivel  superior  representa  lo  que  sabes  y  define  tu

profundidad técnica o especialización. El nivel intermedio abarca lo que sabes que

no  sabes,  el  cual,  junto  con  el  nivel  superior,  conforma  tu  amplitud  técnica  o  la

variedad de temas con los que estás familiarizado. La base, que es la sección más

extensa,  comprende  lo  que  no  sabes  que  no  sabes,  representando  el  vasto

universo  de  conocimientos  cuya  existencia  aún  desconoces.  (Accesibilidad  de  la

imagen)

Figura 2-4. Lo que alguien sabe sobre un tema es la profundidad técnica, y
cuántos temas conoce es la amplitud técnica.

43Para un arquitecto, la amplitud es más importante que la
profundidad. Debido a que los arquitectos deben tomar decisiones
que emparejen las capacidades con las restricciones técnicas, es
valioso tener una comprensión amplia de una gran variedad de
soluciones. Por lo tanto, para un arquitecto, el curso de acción
inteligente es sacrificar algo de la pericia ganada con esfuerzo y usar
ese tiempo para ampliar su portafolio, como se muestra en la Figura
2-5. Algunas áreas de pericia permanecerán, probablemente en
áreas tecnológicas que disfruten especialmente, mientras que otras
se atrofiarán de manera útil.

44Esta  ilustración  presenta  una  pirámide  de  conocimiento  que  ayuda  a  visualizar  el

equilibrio  entre  la  profundidad  y  la  amplitud  de  tus  habilidades.  En  la  cima,  de

color  claro,  se  encuentran  las  cosas  que  sabes,  de  las  cuales  surgen  columnas

hacia  el  siguiente  nivel  que  representan  tus  áreas  de  especialización.  El  nivel

intermedio, en amarillo, contiene las cosas que sabes que no sabes, y el ancho de

estos dos niveles superiores define tu amplitud técnica. Por último, la base de la

pirámide,  en  color  rojizo,  representa  el  vasto  campo  de  las  cosas  que  no  sabes

que no sabes. (Accesibilidad de la imagen)

Figura 2-5. Amplitud aumentada y profundidad reducida para el rol de arquitecto

Nuestra pirámide del conocimiento ilustra cuán fundamentalmente
diferentes son los roles de arquitecto y desarrollador. Los
desarrolladores pasan toda su carrera perfeccionando su pericia.
Transicionar al rol de arquitecto significa un cambio en esa

45perspectiva, algo que a muchas personas les resulta difícil. Esto, a su
vez, conduce a dos disfunciones comunes: primero, un arquitecto
intenta mantener su pericia en una amplia variedad de áreas, sin
lograrlo en ninguna y agotándose en el proceso. Segundo, se
manifiesta como una pericia obsoleta: la sensación errónea de que
tu información anticuada sigue siendo de vanguardia. Vemos esto a
menudo en grandes empresas donde los desarrolladores que
fundaron la compañía han pasado a roles de liderazgo, pero siguen
tomando decisiones tecnológicas utilizando criterios antiguos
(consulta "Antipatrón del cavernícola congelado").

46ANTIPATRÓN DEL CAVERNÍCOLA CONGELADO

Un antipatrón es lo que el programador Andrew Koenig define
como algo que parece una buena idea al empezar, pero que te
mete en problemas. Un antipatrón de comportamiento observado
comúnmente en el mundo real, el antipatrón del cavernícola
congelado, describe a arquitectos que recurren a su
preocupación irracional favorita para cada arquitectura. Por
ejemplo, uno de los colegas de Neal trabajó en un sistema que
presentaba una arquitectura centralizada. Cada vez que
entregaban el diseño a los arquitectos del cliente, la pregunta
persistente era: "¿Pero qué pasa si perdemos a Italia?". Varios
años antes, un extraño problema de comunicación había
impedido que la sede del cliente se comunicara con sus tiendas
en Italia, causando un gran inconveniente. Aunque las
posibilidades de que esto volviera a ocurrir eran extremadamente
pequeñas, los arquitectos se habían obsesionado con esta
característica arquitectónica en particular.

Generalmente, este antipatrón se manifiesta en arquitectos que
han salido perjudicados en el pasado por una mala decisión o un
suceso inesperado, lo que los vuelve particularmente cautelosos
con cualquier cosa relacionada. Si bien la evaluación de riesgos
es importante, también debe ser realista. Comprender la
diferencia entre el riesgo técnico real y el percibido es parte del
proceso de aprendizaje continuo. Pensar como un arquitecto
requiere superar estas ideas y experiencias de "cavernícola
congelado", ver otras soluciones y hacer preguntas más
relevantes.

Los arquitectos deben centrarse en la amplitud técnica para tener un
carcaj más grande del cual sacar flechas. Los desarrolladores que
transicionan al rol de arquitecto pueden tener que cambiar la forma
en que ven la adquisición de conocimientos. Equilibrar la

47profundidad y la amplitud de su portafolio de conocimientos es algo
que cada desarrollador debería considerar a lo largo de su carrera.
Pero, ¿cómo obtiene un arquitecto amplitud técnica? Las siguientes
secciones proporcionan algunas técnicas que te ayudarán a
descubrir las "cosas que no sabes que no sabes".

La regla de los 20 minutos

Como se ilustra en la Figura 2-5, la amplitud técnica es más
importante para los arquitectos que la profundidad técnica. Pero,
¿cómo te mantienes al día con todas las últimas tendencias y
términos de moda mientras trabajas a tiempo completo, desarrollas
tu carrera, pasas tiempo con amigos y cuidas de tu familia?

Una técnica que utilizamos es la regla de los 20 minutos. La idea es
dedicar al menos 20 minutos al día a aprender algo nuevo o
profundizar en un tema específico. La Figura 2-6 ilustra algunos
buenos lugares para invertir tus 20 minutos, como InfoQ, DZone
Refcardz y el Thoughtworks Technology Radar. Puedes aprender más
sobre términos desconocidos buscándolos en internet, promoviendo
ese conocimiento de "las cosas que no sabes que no sabes" a "las
cosas que sabes que no sabes". Incluso podrías dedicar ese tiempo
a leer un libro como este. El punto es reservar algo de tiempo en tu
ajetreado día para enfocarte en desarrollar tu amplitud técnica y, por
ende, tu carrera.

48Esta  imagen  ilustra  la  regla  de  los  veinte  minutos  para  el  aprendizaje  continuo,

mostrando  un  cronómetro  con  una  sección  resaltada  en  verde  que  marca  ese

intervalo  de  tiempo.  Debajo  del  reloj,  se  presentan  tres  recursos  clave  para

mantenerte actualizado: el portal InfoQ, el Radar Tecnológico de Thoughtworks y

DZone Refcardz, que se describe como la biblioteca de guías rápidas técnicas más

grande  del  mundo.  Cada  logotipo  incluye  su  respectiva  dirección  web,  sugiriendo

estas plataformas como herramientas ideales para dedicar un breve tiempo diario

a mejorar tu conocimiento técnico y profesional. (Accesibilidad de la imagen)

Figura 2-6. La regla de los 20 minutos

Muchos tecnólogos, cuando adoptan este concepto por primera vez,
planean sus 20 minutos para el almuerzo o para después del
trabajo; sin embargo, en nuestra experiencia, estos periodos de
tiempo rara vez funcionan. Es fácil empezar a usar las horas del
almuerzo para ponerse al día con el trabajo en lugar de tomar un
descanso, y las noches son aún peores, con planes sociales, tiempo
en familia y más después de un largo día. En cambio,
recomendamos encarecidamente tomar tus 20 minutos a primera
hora de la mañana, justo después de tomar una taza de café o té y,
lo que es más importante, antes de revisar tu correo electrónico.

49Una vez que revisas el correo, tu mañana terminó y tu día ha
comenzado. Dedica tus 20 minutos mientras tu mente está fresca y
antes de que las distracciones tomen el control.

Seguir la regla de los 20 minutos aumentará tu amplitud técnica y te
ayudará a desarrollar y mantener el conocimiento que te convertirá
en un arquitecto de software eficaz.

Desarrollar un radar personal

Durante la mayor parte de los años 90 y principios de los 2000, uno
de tus autores fue el CTO de una pequeña empresa de formación y
consultoría. Cuando empezó allí, la plataforma principal era Clipper,
una herramienta de desarrollo rápido de aplicaciones para construir
aplicaciones DOS sobre archivos dBASE. Hasta que un día
desapareció. La empresa había notado el auge de Windows, pero el
mercado empresarial seguía siendo DOS... hasta que abruptamente
dejó de serlo. Un compañero de trabajo se lamentaba de que no
podían tomar su enorme cuerpo de conocimientos de Clipper, ahora
inútiles, y reemplazarlos por otra cosa. ¿Ha habido algún grupo en la
historia, se preguntaba el colega, que haya aprendido y desechado
tanto conocimiento detallado en sus vidas como lo hacen los
desarrolladores de software? La experiencia dejó una impresión
duradera: ignora el avance de la tecnología bajo tu propio riesgo.

También nos enseñó una lección importante sobre las burbujas
tecnológicas. Cuando los desarrolladores, arquitectos y otros
tecnólogos nos involucramos profundamente en una tecnología
específica, volcando nuestro trabajo y pensamiento en ella,
tendemos a vivir en una burbuja memética. Dentro de la burbuja,
que también sirve como cámara de eco, todos conocen y se
preocupan por esa tecnología tanto como nosotros. Es posible que ni
siquiera veamos evaluaciones honestas desde fuera de la burbuja,
especialmente si la burbuja fue creada por un proveedor de

50tecnología en primer lugar. Y cuando la burbuja comienza a colapsar,
no hay advertencia hasta que es demasiado tarde.

Lo que nos falta en nuestra burbuja es un radar tecnológico: un
documento vivo que nos ayude a evaluar los riesgos y recompensas
de las tecnologías existentes y nacientes. El concepto de radar
proviene de Thoughtworks, donde Neal se desempeña como director
y arquitecto de software. En esta sección, describiremos cómo surgió
este concepto y luego te mostraremos cómo crear un radar personal.

El Thoughtworks Technology Radar

El Technology Advisory Board (TAB) es un grupo de líderes
tecnológicos sénior dentro de Thoughtworks que asiste al CTO en la
toma de decisiones sobre direcciones y estrategias tecnológicas para
la empresa y sus clientes. Para mantenerse al día, este grupo
comenzó a producir lo que ahora es un Technology Radar (Radar
Tecnológico) semestral.

Esto tuvo efectos secundarios inesperados. Cuando Neal hablaba en
conferencias, los asistentes comenzaron a buscarlo para agradecerle
por ayudar a producir el Radar, añadiendo a menudo que su
empresa había empezado a producir su propia versión. Neal también
se dio cuenta de que esta era la respuesta a una pregunta que se
hacía constantemente en los paneles de conferencistas: "¿Cómo te
mantienes al día con la tecnología? ¿Cómo determinas qué camino
seguir después?". La respuesta, por supuesto, es que todos los
conferencistas tienen alguna forma de radar interno.

Partes

El Radar de Thoughtworks consta de cuatro cuadrantes que intentan
cubrir la mayor parte del panorama del desarrollo de software:

Herramientas (Tools)

Todo, desde herramientas de desarrollo como los IDE hasta
herramientas de integración de grado empresarial.

51Lenguajes y frameworks (Languages and frameworks)

Lenguajes de programación, librerías y frameworks,
típicamente de código abierto.

Técnicas (Techniques)

Cualquier práctica que asista al desarrollo de software en
general, incluyendo procesos, prácticas de ingeniería y
consejos.

Plataformas (Platforms)

Plataformas tecnológicas, incluyendo bases de datos,
proveedores de la nube y sistemas operativos.

Anillos

El Radar tiene cuatro anillos, enumerados aquí desde el exterior
hacia el interior:

Hold (Mantener en espera)

El signiﬁcado original del anillo "Hold" era "esperar por
ahora", para representar tecnologías que eran demasiado
nuevas para ser evaluadas razonablemente todavía;
tecnologías que estaban generando mucho ruido pero que
aún no habían sido probadas. El anillo "Hold" ha
evolucionado y ahora indica algo más como "no empieces
nada nuevo con esta tecnología". No hay problema en usarla
en proyectos existentes, pero piénsalo dos veces antes de
usarla para nuevos desarrollos.

Assess (Evaluar)

El anillo "Assess" indica que vale la pena explorar una
tecnología (por ejemplo, a través de picos de desarrollo,
proyectos de investigación o sesiones en conferencias) para
ver cómo afectará a la organización. Por ejemplo, cuando los

52navegadores móviles cobraron importancia, muchas
grandes empresas pasaron visiblemente por esta fase al
formular una estrategia móvil.

Trial (Probar)

El anillo "Trial" es para tecnologías que vale la pena seguir.
Si una capacidad está en este anillo, es importante entender
cómo construirla. Ahora es el momento de realizar un
proyecto piloto de bajo riesgo.

Adopt (Adoptar)

Thoughtworks cree ﬁrmemente que la industria debería
adoptar los elementos enumerados en el anillo "Adopt".

En la vista de ejemplo del Radar en la Figura 2-7, cada "blip" (punto)
representa una tecnología o técnica diferente. Si bien Thoughtworks
utiliza el radar para difundir sus opiniones colectivas sobre el mundo
del software, muchos desarrolladores y arquitectos también lo usan
como una forma de estructurar su proceso de evaluación tecnológica
y organizar su pensamiento sobre en qué invertir tiempo. Para uso
personal, sugerimos alterar los significados de los cuadrantes por los
siguientes:

Hold (Mantener en espera)

Esto puede incluir no solo tecnologías y técnicas a evitar,
sino también hábitos que estés tratando de romper. Por
ejemplo, si eres un arquitecto del mundo de .NET, podrías
estar acostumbrado a leer las últimas noticias y chismes en
foros sobre los pormenores de los equipos. Aunque sea
entretenido, esto puede ser un ﬂujo de información de bajo
valor. Colocarlo en el anillo "Hold" sirve como un
recordatorio de lo que quieres evitar.

Assess (Evaluar)

53Usa el anillo "Assess" para tecnologías prometedoras de las
que hayas escuchado cosas buenas pero para las que aún no
has tenido tiempo de evaluar por ti mismo. Este anillo forma
un área de preparación para investigaciones futuras más
serias.

Trial (Probar)

El anillo "Trial" indica investigación y desarrollo activos,
como realizar experimentos de prueba (spikes) dentro de
una base de código más grande. Estas son tecnologías en las
que vale la pena invertir tiempo para comprenderlas más
profundamente y así poder incluirlas eﬁcazmente en el
análisis de compensaciones (trade-oﬀs).

Adopt (Adoptar)

Tu anillo personal "Adopt" representa las cosas nuevas que
más te entusiasman y las mejores prácticas para resolver
problemas particulares.

54Esta  gráfica  muestra  un  radar  de  tecnología  dividido  en  cuatro  secciones

principales: Técnicas, Lenguajes y marcos de trabajo, Herramientas y Plataformas.

La  estructura  se  organiza  a  través  de  cuatro  anillos  concéntricos  que  indican  el

estado  de  madurez  o  recomendación  de  cada  elemento;  desde  el  centro  hacia

afuera,  estos  niveles  son  Adoptar,  Probar,  Evaluar  y  Mantener.  Dentro  de  cada

cuadrante,  se  distribuyen  múltiples  iconos  numerados  con  formas  circulares  y

triangulares  que  representan  diversas

tecnologías,  prácticas  o  productos

específicos, cuya ubicación dentro de los anillos sugiere qué tan conveniente es su

implementación o estudio en el panorama actual. (Accesibilidad de la imagen)

Figura 2-7. Un ejemplo de un Thoughtworks Technology Radar

La mayoría de los tecnólogos eligen tecnologías de manera más o
menos improvisada, basándose en lo que está de moda o en lo que
usan sus empleadores, pero es peligroso para tu carrera adoptar una
actitud de "dejar hacer" hacia tu portafolio tecnológico. Crear un
radar tecnológico te ayuda a formalizar tu pensamiento sobre la

55tecnología y a equilibrar criterios de decisión opuestos. (Por ejemplo,
podría ser más difícil conseguir un nuevo trabajo centrado en la
tecnología "más genial", mientras que una tecnología más
establecida podría tener un mercado laboral enorme pero ofrecer un
trabajo menos interesante).

Trata tu portafolio tecnológico como un portafolio financiero:
¡diversifica! Elige algunas tecnologías y/o habilidades que tengan
una gran demanda y haz un seguimiento de esa demanda. Pero
también podrías querer probar algunas apuestas tecnológicas, como
la IA generativa o los dispositivos IoT integrados. Abundan las
anécdotas sobre desarrolladores que se liberaron de la servidumbre
del cubículo trabajando tarde por la noche en proyectos de código
abierto que se volvieron populares y, finalmente, rentables. Esta es
otra razón más para enfocarse en la amplitud en lugar de en la
profundidad.

Construir un radar personal proporciona un buen andamiaje para
ampliar tu portafolio tecnológico; pero, en última instancia, el
ejercicio es más importante que el resultado. Crear la visualización
del radar te da una excusa para reservar tiempo en tu ajetreada
agenda para pensar en estas cosas, lo cual suele ser la única forma
de llevar a cabo este tipo de reflexión.

Aunque la parte más importante de construir tu radar personal son
las conversaciones que genera, también produce algunas
visualizaciones muy útiles. Tras la gran demanda de los tecnólogos
que construían sus propias visualizaciones de radar, Thoughtworks
lanzó una herramienta llamada Build Your Own Radar. Con una hoja
de cálculo de Google como entrada, genera una visualización que
muestra tu radar personal. Animamos a todos los tecnólogos a
aprovecharla .

56Analizar las compensaciones (Trade-Offs)

Pensar como un arquitecto se trata de ver las compensaciones
(trade-offs) en cada solución, técnica o de otro tipo, y analizar esas
compensaciones para determinar la mejor solución. La razón por la
que esta es una de las actividades críticas de un arquitecto (y, por
tanto, parte del pensamiento arquitectónico) se ejemplifica con la
siguiente cita de Mark (uno de tus autores):

La arquitectura es aquello que no puedes buscar en Google ni
preguntarle a un LLM.

—Mark Richards

Todo en la arquitectura es una compensación, razón por la cual la
famosa respuesta a cada pregunta de arquitectura en el universo es
"Depende". Aunque esta respuesta pueda ser molesta,
lamentablemente es cierta. No puedes buscar en Google ni
preguntarle a un motor de IA o a un modelo de lenguaje extenso
(LLM) si REST o la mensajería serían mejores para tu sistema, o si
los microservicios son el estilo de arquitectura adecuado para tu
nuevo producto, porque la respuesta sí depende. Depende del
entorno de despliegue, los impulsores de negocio, la cultura de la
empresa, los presupuestos, los plazos, el conjunto de habilidades de
los desarrolladores y docenas de otros factores. El entorno, la
situación y el problema de cada persona serán diferentes. Por eso la
arquitectura es tan difícil. Para citar a Neal, tu otro autor:

No hay respuestas correctas o incorrectas en la arquitectura, solo
compensaciones.

—Neal Ford

Por ejemplo, considera un sistema de subasta de artículos (Figura 2-
8) donde los postores en línea pujan por los artículos que se
subastan. El servicio Bid Producer (Productor de pujas) genera
una puja del postor y luego envía ese monto de la puja a los

57servicios Bid Capture (Captura de pujas), Bid Tracking
(Seguimiento de pujas) y Bid Analytics (Análisis de pujas).

Este  diagrama  ilustra  el  flujo  de  datos  en  un  sistema  de  subastas  donde  un

Productor de ofertas envía una oferta de artículo hacia tres componentes distintos.

Puedes  observar  cómo  la  información  se  distribuye  desde  el  bloque  emisor  en  la

izquierda  hacia  los  servicios  de  Captura  de  ofertas,  Seguimiento  de  ofertas  y

Análisis  de  ofertas  situados  a  la  derecha.  La  imagen  utiliza  flechas  para

representar  la  comunicación  unidireccional,  mostrando  cómo  un  solo  evento  de

puja  es  procesado  simultáneamente  por  múltiples  servicios  especializados  dentro

de la arquitectura. (Accesibilidad de la imagen)

Figura 2-8. Ejemplo de sistema de subasta de una compensación: ¿colas o
tópicos?

Para el comportamiento asíncrono en este sistema, un arquitecto
podría usar colas al estilo de mensajería punto a punto, o usar un
tópico al estilo de mensajería de publicación y suscripción. ¿Cuál
deberían elegir? No pueden buscar la respuesta en Google. El
pensamiento arquitectónico les exige analizar las compensaciones
asociadas con cada opción y seleccionar la mejor (o la menos mala)
opción dada la situación específica.

Las dos opciones de mensajería para el sistema de subasta de
artículos se muestran en la Figura 2-9, que ilustra el uso de tópicos
en un modelo de mensajería de publicación y suscripción, y la Figura

582-10, que representa el uso de colas en un modelo de mensajería
punto a punto.

Este diagrama ilustra un modelo de comunicación entre servicios mediante el uso

de un tema de mensajería. En la parte izquierda, el productor de ofertas envía una

señal  que  representa  la  oferta  de  un  artículo  hacia  un  componente  central

etiquetado como tema. Desde este punto centralizado, la información se distribuye

simultáneamente  a  través  de  flechas  hacia  tres  servicios  distintos  situados  a  la

derecha: captura de ofertas, seguimiento de ofertas y analítica de ofertas, lo que

permite  que  múltiples  consumidores  reciban  el  mismo  mensaje  de  manera

asíncrona. (Accesibilidad de la imagen)

Figura 2-9. Uso de un tópico para la comunicación entre servicios

59Esta imagen ilustra un modelo de comunicación punto a punto en un sistema de

subastas,  donde  observas  cómo  un  Productor  de  ofertas  envía  simultáneamente

una oferta de artículo a tres componentes distintos etiquetados como Cola. Cada

uno  de  estos  conductos  transporta  la  información  hacia  un  destino  específico:  la

Captura  de  ofertas,  el  Seguimiento  de  ofertas  y  la  Analítica  de  ofertas.  En  este

esquema,  notas  que  el  productor  debe  establecer  y  gestionar  una  conexión

individualizada  para  cada  servicio  que  requiera  los  datos,  lo  que  representa  una

estructura  de  acoplamiento  directo  entre  los  distintos  módulos  del  sistema.

(Accesibilidad de la imagen)

Figura 2-10. Uso de colas para la comunicación entre servicios

La clara ventaja (y la solución aparentemente obvia) a este
problema en la Figura 2-9 es la extensibilidad arquitectónica. El
servicio Bid Producer (Productor de pujas) solo requiere una
única conexión a un tópico. Compara eso con la solución de colas en
la Figura 2-10, donde el Bid Producer necesita conectarse a tres
colas diferentes. Si se añadiera un nuevo servicio llamado Bid
History (Historial de pujas) a este sistema (para proporcionar a

60cada postor un historial de todas sus pujas), no se necesitarían
cambios en los servicios o la infraestructura existentes. El nuevo
servicio Bid History simplemente podría suscribirse al tópico que ya
contiene la información de las pujas.

Sin embargo, con la opción de colas mostrada en la Figura 2-10, el
servicio Bid History requeriría una nueva cola, y el Bid Producer
tendría que modificarse para añadir una conexión adicional a la
nueva cola. El punto aquí es que el uso de colas significa que añadir
nueva funcionalidad de pujas requiere cambios significativos en los
servicios y la infraestructura, mientras que con el enfoque de
tópicos, no se necesitan cambios en la infraestructura existente.
Además, el Bid Producer está menos acoplado en la opción de
tópicos, donde el Bid Producer no sabe cómo se utilizará la
información de las pujas ni por qué servicios. En la opción de colas,
el Bid Producer sabe exactamente cómo se utilizará la información
de las pujas (y por quién) y, por lo tanto, está más acoplado al
sistema.

Hasta ahora, este análisis de compensaciones parece dejar claro que
el enfoque de tópicos utilizando el modelo de mensajería de
publicación y suscripción es la opción obvia y la mejor. Sin embargo,
para citar a Rich Hickey, el creador del lenguaje de programación
Clojure:

Los programadores conocen los beneficios de todo y las
compensaciones de nada. Los arquitectos necesitan entender
ambos.

—Rich Hickey

Pensar arquitectónicamente significa no solo mirar los beneficios de
una solución determinada, sino también analizar los aspectos
negativos asociados, o las compensaciones. Continuando con el
ejemplo del sistema de subasta, un arquitecto de software analizaría
tanto los aspectos negativos como los positivos de la solución de
tópicos. En la Figura 2-9, puedes ver que con un tópico, cualquiera

61puede acceder a los datos de las pujas, lo que introduce un posible
problema con el acceso y la seguridad de los datos. Sin embargo, en
el modelo de colas ilustrado en la Figura 2-10, los datos enviados a
la cola solo pueden ser accedidos por el consumidor específico que
recibe ese mensaje. Si un servicio malicioso intentara escuchar una
cola, el servicio correspondiente no recibiría esas pujas, y se enviaría
inmediatamente una notificación sobre la pérdida de datos (y una
posible brecha de seguridad). En otras palabras, es muy fácil
"pinchar" un tópico, pero no una cola.

Además del problema de seguridad, la solución de tópicos en la
Figura 2-9 solo admite contratos homogéneos. Todos los servicios
que reciben los datos de las pujas deben aceptar el mismo contrato
de datos y el mismo conjunto de datos de pujas. En la opción de
colas, cada consumidor puede tener su propio contrato, específico
para los datos que necesita. Por ejemplo, supongamos que el nuevo
servicio Bid History (Historial de pujas) requiere el precio de
venta actual junto con la puja, pero ningún otro servicio necesita esa
información. En este caso, el contrato tendría que modificarse,
afectando a todos los demás servicios que utilizan esos datos. En el
modelo de colas, este sería un canal separado y, por lo tanto, un
contrato separado que no afecta a ningún otro servicio.

Otra desventaja del modelo de tópicos es que no admite el
monitoreo de la cantidad de mensajes en el tópico, por lo que no
puede admitir capacidades de autoescalado. Sin embargo, con la
opción de colas, cada cola puede ser monitoreada individualmente y
se puede aplicar un balanceo de carga programático a cada
consumidor de pujas, de modo que cada uno pueda escalarse
automáticamente de forma independiente. Ten en cuenta que esta
compensación es específica de la tecnología: el Protocolo Avanzado
de Cola de Mensajes (AMQP) puede admitir el balanceo de carga
programático y el monitoreo debido a la separación entre un
intercambio (al que el productor envía) y una cola (a la que el
consumidor escucha).

62Dado este análisis de compensaciones más completo, ¿cuál es la
mejor opción?

¡Depende! La Tabla 2-1 resume estas compensaciones.

Tabla 2-1. Compensaciones para los tópicos

Ventajas de los
tópicos

Desventajas de los tópicos

Extensibilidad
arquitectónica

Preocupaciones sobre el acceso y la
seguridad de los datos

Desacoplamiento de
servicios

Sin contratos heterogéneos

Monitoreo y escalabilidad programática

Nuevamente, todo en la arquitectura de software tiene
compensaciones: ventajas y desventajas. Pensar como un arquitecto
significa analizar estas compensaciones y luego hacer preguntas
como: "¿Qué es más importante: la extensibilidad o la seguridad?".
La elección de un arquitecto siempre dependerá de los impulsores
de negocio, el entorno y una serie de otros factores.

Comprender los impulsores de negocio

Pensar como un arquitecto también significa comprender los
impulsores de negocio necesarios para el éxito del sistema y traducir
esos requisitos en características de arquitectura como la
escalabilidad, el rendimiento y la disponibilidad. Esta es una tarea
desafiante que requiere que el arquitecto tenga cierto conocimiento
del dominio de negocio y relaciones saludables y colaborativas con
los interesados (stakeholders) clave del negocio. Hemos dedicado

63cuatro capítulos del libro a este tema específico: en el Capítulo 4,
definimos varias características de arquitectura. En el Capítulo 5,
describimos formas de identificar y calificar las características de
arquitectura. En el Capítulo 6, describimos cómo medir cada
característica para asegurar que se cumplan las necesidades de
negocio del sistema. Y finalmente, en el Capítulo 7, discutimos el
alcance de las características arquitectónicas y cómo se relacionan
con el acoplamiento.

Equilibrar la arquitectura y la programación
práctica

Una de las tareas difíciles a las que se enfrenta un arquitecto es
cómo equilibrar la programación práctica (hands-on coding) con la
arquitectura de software. Creemos firmemente que cada arquitecto
debería programar y mantener un cierto nivel de profundidad técnica
(ver "Amplitud técnica"). Aunque esto pueda parecer una tarea fácil,
a veces es bastante difícil de lograr.

Nuestro primer consejo para cualquiera que se esfuerce por
equilibrar la programación práctica con ser un arquitecto de software
es evitar la Trampa del cuello de botella (Bottleneck Trap). El
antipatrón de la Trampa del cuello de botella ocurre cuando un
arquitecto se adueña del código dentro del camino crítico de un
sistema (usualmente el código del framework subyacente o algunas
de las partes más complicadas) y se convierte en un cuello de
botella para el equipo. Esto sucede porque el arquitecto no es un
desarrollador a tiempo completo y, por lo tanto, debe equilibrar el
trabajo de desarrollo (como escribir y probar código fuente) con el
rol de arquitecto (dibujar diagramas, asistir a reuniones y, bueno,
asistir a más reuniones).

Una forma de evitar la Trampa del cuello de botella es que el
arquitecto delegue las partes críticas del sistema a otros miembros
del equipo de desarrollo y luego se concentre en programar una

64pieza menor de funcionalidad de negocio (como un servicio o una
pantalla de interfaz de usuario) para dentro de una a tres
iteraciones. Esto tiene tres efectos positivos. Primero, el arquitecto
gana experiencia práctica escribiendo código de producción mientras
evita convertirse en un cuello de botella para el equipo. Segundo, el
camino crítico y el código del framework se distribuyen al equipo de
desarrollo (que es donde pertenecen), otorgando al equipo la
propiedad y una mejor comprensión de las partes más difíciles del
sistema. Tercero, y quizás lo más importante, el arquitecto está
escribiendo el mismo código fuente relacionado con el negocio que
el equipo de desarrollo. Esto les ayuda a identificarse mejor con los
puntos de dolor del equipo de desarrollo en relación con los
procesos, los procedimientos y el entorno de desarrollo (y, con
suerte, trabajar para mejorar esas cosas).

Supongamos, sin embargo, que el arquitecto no puede desarrollar
código con el equipo de desarrollo. ¿Cómo pueden seguir siendo
prácticos y mantener cierto nivel de profundidad técnica? A
continuación, se presentan algunos consejos y técnicas para
arquitectos que desean seguir profundizando en sus habilidades
técnicas:

Pruebas de concepto frecuentes

Realizar pruebas de concepto (POC) frecuentes requiere que
el arquitecto escriba código fuente; también ayuda a validar
una decisión de arquitectura al tener en cuenta los detalles
de implementación. Por ejemplo, supongamos que un
arquitecto se queda atascado tratando de elegir entre dos
soluciones de almacenamiento en caché. Una forma efectiva
de ayudar a tomar esta decisión es desarrollar un ejemplo
funcional en cada producto de caché y comparar los
resultados. Esto permite al arquitecto ver de primera mano
los detalles de implementación y la cantidad de esfuerzo
requerido para desarrollar la solución completa. También
les permite comparar mejor las características

65arquitectónicas entre las diferentes soluciones de caché,
como la escalabilidad, el rendimiento y la tolerancia a fallos
en general.

Siempre que sea posible, el arquitecto debe escribir el código
de mejor calidad de producción que pueda. Recomendamos
esta práctica por dos razones. Primero, muy a menudo, el
código de una prueba de concepto "desechable" termina en
el repositorio de código fuente y se convierte en la
arquitectura de referencia o el ejemplo guía que otros deben
seguir. Lo último que cualquier arquitecto querría es que su
código desechable y descuidado sea tratado como
representativo de su calidad de trabajo habitual. Segundo,
escribir código de prueba de concepto con calidad de
producción signiﬁca practicar la escritura de código de
calidad y bien estructurado, en lugar de desarrollar
continuamente malas prácticas de programación al crear
POC rápidas y descuidadas.

Abordar la deuda técnica

Otra forma en que los arquitectos pueden seguir siendo
prácticos es abordando algo de deuda técnica, liberando al
equipo de desarrollo para que trabaje en las historias de
usuario funcionales críticas. La deuda técnica suele ser de
baja prioridad, por lo que si el arquitecto no tiene la
oportunidad de completar una tarea de deuda técnica
dentro de una iteración determinada, no es el ﬁn del mundo
y, por lo general, no afectará el éxito de la iteración.

Corregir errores (Bugs)

De manera similar, trabajar en la corrección de errores
dentro de una iteración es otra forma de mantener las
habilidades de programación práctica mientras se ayuda al
equipo de desarrollo. Aunque ciertamente no es glamoroso,

66esta técnica permite al arquitecto identiﬁcar problemas y
debilidades dentro de la base de código y posiblemente de la
arquitectura.

Automatizar

Aprovechar la automatización mediante la creación de
herramientas simples de línea de comandos y analizadores
para ayudar al equipo de desarrollo con sus tareas
cotidianas es otra excelente manera de mantener las
habilidades de programación práctica mientras se hace que
el equipo de desarrollo sea más eﬁcaz. Busca tareas
repetitivas que realice el equipo de desarrollo y
automatízalas. Te agradecerán la automatización. Algunos
ejemplos son los validadores automáticos de código fuente
para ayudar a veriﬁcar estándares de codiﬁcación
especíﬁcos que no se encuentran en otras pruebas de lint,
listas de veriﬁcación automatizadas y tareas manuales
repetitivas de refactorización de código.

La automatización en forma de análisis arquitectónico y
funciones de aptitud para asegurar la vitalidad y el
cumplimiento de la arquitectura es otra gran manera de
mantenerse práctico. Por ejemplo, un arquitecto puede
escribir código Java en ArchUnit en la plataforma Java para
automatizar el cumplimiento arquitectónico, o funciones de
aptitud personalizadas para asegurar el cumplimiento
arquitectónico mientras gana experiencia práctica.
Hablamos de estas técnicas en el Capítulo 6.

Hacer revisiones de código

Una técnica ﬁnal para seguir siendo práctico como
arquitecto es realizar revisiones de código frecuentes.
Aunque el arquitecto no esté escribiendo código en realidad,
esto al menos lo mantiene involucrado en el código fuente.

67Otros beneﬁcios de las revisiones de código incluyen
asegurar el cumplimiento de la arquitectura e identiﬁcar
oportunidades de mentoría y entrenamiento en el equipo.

Hay más en el pensamiento arquitectónico

Este capítulo constituye los aspectos fundamentales para empezar a
pensar como un arquitecto. Sin embargo, hay mucho más en el
hecho de pensar como un arquitecto de lo que se describe en este
capítulo. Pensar como un arquitecto implica comprender la
estructura general de un sistema (cubriremos ese tema a
continuación en el Capítulo 3), comprender las inquietudes de
negocio y traducirlas en características arquitectónicas (tenemos
cuatro capítulos sobre ese tema) y, finalmente, ver un sistema a
través de sus componentes lógicos: los bloques de construcción de
un sistema (discutiremos ese tema en el Capítulo 8).

68Capítulo 3. Modularidad

Los arquitectos y desarrolladores han luchado con el concepto de
modularidad durante bastante tiempo, como es evidente en esta cita
de Diseño Compuesto/Estructurado (Van Nostrand Reinhold, 1978):

El 95% de las palabras [escritas sobre arquitectura de software]
se dedican a ensalzar los beneficios de la “modularidad” y poco, si
es que algo, se dice sobre cómo lograrla.

—Glenford J. Myers

Diferentes plataformas ofrecen diferentes mecanismos de
reutilización de código, pero todas admiten alguna forma de agrupar
el código relacionado en módulos. Aunque este concepto es
universal en la arquitectura de software, ha resultado difícil de
definir. Una búsqueda casual en Internet arroja docenas de
definiciones, sin consistencia (y con algunas contradicciones). Este
no es un problema nuevo. Sin embargo, como no existe una
definición reconocida, debemos entrar en la pelea y proporcionar
nuestras propias definiciones en aras de la consistencia a lo largo del
libro.

Comprender la modularidad y sus muchas encarnaciones en la
plataforma de desarrollo elegida es fundamental para los
arquitectos. Muchas de las herramientas que tenemos para analizar
la arquitectura (como las métricas, las funciones de fitness y las
visualizaciones) dependen de la modularidad y conceptos
relacionados. La modularidad es un principio organizativo. Si un
arquitecto diseña un sistema sin prestar atención a cómo se
conectan las piezas, ese sistema presentará innumerables
dificultades. Para usar una analogía física, los sistemas de software
modelan sistemas complejos, que tienden hacia la entropía (o el
desorden). En un sistema físico, se debe añadir energía para

69preservar el orden. Lo mismo ocurre con los sistemas de software:
los arquitectos deben gastar energía constantemente para asegurar
la solidez estructural, lo cual no sucederá por accidente.

Preservar una buena modularidad ejemplifica nuestra definición de
una característica de arquitectura implícita: prácticamente ningún
requisito de proyecto le pide explícitamente al arquitecto que
asegure una buena distinción y comunicación modular, pero las
bases de código sostenibles sí requieren el orden y la consistencia
que esto aporta.

Modularidad frente a granularidad

Los desarrolladores y arquitectos a menudo usan los términos
modularidad y granularidad indistintamente, aunque sus significados
son muy diferentes. La modularidad se trata de desglosar los
sistemas en piezas más pequeñas, como pasar de un estilo de
arquitectura monolítico (como la arquitectura tradicional de capas n-
tier) a un estilo de arquitectura altamente distribuido, como los
microservicios. La granularidad, por otro lado, se trata del tamaño
de esas piezas: qué tan grande debería ser una parte particular del
sistema (o servicio). Sin embargo, como se afirma en la siguiente
cita de uno de tus autores, es con la granularidad donde los
arquitectos y desarrolladores se meten en problemas:

Adopta la modularidad, pero ten cuidado con la granularidad.

—Mark Richards

La granularidad provoca que los servicios o componentes se acoplen
entre sí, creando antipatrones de arquitectura complejos y difíciles
de mantener como la Arquitectura Espagueti, los Monolitos
Distribuidos y la famosa Gran Bola de Lodo Distribuida. El truco para
evitar estos antipatrones arquitectónicos es prestar atención a la
granularidad y al nivel general de acoplamiento entre servicios y
componentes.

70Definiendo la modularidad

Merriam-Webster define un módulo como "cada una de las partes
estandarizadas o unidades independientes de un conjunto que
pueden utilizarse para construir una estructura más compleja". Por el
contrario, en este libro, utilizamos la modularidad para describir una
agrupación lógica de código relacionado, que podría ser un grupo de
clases en un lenguaje orientado a objetos o un grupo de funciones
en un lenguaje estructurado o funcional. Los desarrolladores suelen
utilizar los módulos como una forma de agrupar código relacionado.
Por ejemplo, el paquete com.mycompany.customer en Java debería
contener elementos relacionados con los clientes. La mayoría de los
lenguajes proporcionan mecanismos para la modularidad (package
en Java, namespace en .NET, etc.).

Los lenguajes de programación modernos cuentan con una amplia
variedad de mecanismos de empaquetado, y a muchos
desarrolladores les resulta difícil elegir entre ellos. Por ejemplo, en
muchos lenguajes modernos, los desarrolladores pueden definir el
comportamiento en funciones/métodos, clases o paquetes/espacios
de nombres (namespaces), cada uno con diferentes reglas de
visibilidad y alcance. Algunos lenguajes complican esto aún más al
añadir constructos de programación, como el protocolo de
metaobjetos (metaobject protocol), para proporcionar aún más
mecanismos de extensión.

Los arquitectos deben ser conscientes de cómo los desarrolladores
empaquetan las cosas, porque el empaquetado tiene implicaciones
importantes en la arquitectura. Por ejemplo, si varios paquetes están
estrechamente acoplados, reutilizar uno de ellos para un trabajo
relacionado se vuelve más difícil.

71REUTILIZACIÓN MODULAR ANTES DE LAS CLASES

Los desarrolladores que se formaron en los días previos a los
lenguajes orientados a objetos pueden preguntarse por qué
existen tantos esquemas de separación diferentes. Gran parte de
la razón tiene que ver con la compatibilidad hacia atrás; no del
código, sino de cómo los desarrolladores piensan sobre las cosas.

En marzo de 1968, la revista Communications of the Association
for Computing Machinery (ACM) publicó un artículo del científico
de la computación Edsger Dijkstra titulado “Go To Statement
Considered Harmful” (La sentencia Go To se considera
perjudicial). Él denigraba el uso común de la sentencia GOTO,
habitual en los lenguajes de programación de la época, porque
permitía saltos no lineales dentro del código, lo que dificultaba el
razonamiento y la depuración.

El artículo de Dijkstra ayudó a marcar el comienzo de la era de
los lenguajes de programación estructurados a mediados de la
década de 1970, ejemplificados por Pascal y C, que fomentan un
pensamiento más profundo sobre cómo encajan las cosas. Los
desarrolladores pronto se dieron cuenta de que la mayoría de los
lenguajes de programación no ofrecían una buena forma de
agrupar cosas similares de manera lógica. Así, a mediados de la
década de 1980 nació la breve era de los lenguajes modulares,
como Modula (el siguiente lenguaje del creador de Pascal,
Niklaus Wirth) y Ada. Estos lenguajes adoptaron el constructo de
programación del módulo, de forma muy parecida a como
pensamos hoy en los paquetes o espacios de nombres (pero sin
las clases).

Sin embargo, la era de la programación modular de mediados de
la década de 1980 fue breve porque los lenguajes orientados a
objetos se popularizaron y ofrecieron nuevas formas de
encapsular y reutilizar código. Aun así, los diseñadores de
lenguajes se dieron cuenta de la utilidad de los módulos y los

72conservaron en forma de paquetes y espacios de nombres.
Muchos lenguajes todavía contienen características de
compatibilidad que hoy parecen extrañas pero que se
introdujeron para soportar estos diferentes paradigmas. Por
ejemplo, Java admite paradigmas modulares (a través de
paquetes e inicialización a nivel de paquete usando
inicializadores estáticos), así como paradigmas orientados a
objetos y funcionales, cada uno con sus propias reglas de
alcance y peculiaridades.

En las discusiones sobre arquitectura de este libro, usamos
modularidad como un término general para denotar una agrupación
relacionada de código: clases, funciones o cualquier otra agrupación.
Esto no implica una separación física, sino simplemente una lógica.
(La diferencia es a veces importante). Por ejemplo, agrupar una gran
cantidad de clases en una aplicación monolítica puede ser
conveniente; sin embargo, cuando llega el momento de
reestructurar la arquitectura, el acoplamiento fomentado por una
partición laxa puede impedir los esfuerzos para desglosar el
monolito. Por eso es útil hablar de la modularidad como un
concepto, independiente de la separación física que una plataforma
en particular fuerza o implica.

Vale la pena discutir el concepto general de espacio de nombres
(namespace), que es independiente de la implementación técnica en
la plataforma .NET que también se llama espacio de nombres. Los
desarrolladores a menudo necesitan nombres precisos y totalmente
calificados para diferentes activos de software (componentes, clases,
etc.) para separarlos entre sí. El ejemplo más obvio que la gente usa
todos los días es el internet, que se basa en identificadores globales
únicos vinculados a direcciones IP.

La mayoría de los lenguajes tienen algún mecanismo de modularidad
que funciona como un espacio de nombres para organizar cosas
como variables, funciones o métodos. A veces, la estructura del

73módulo se refleja físicamente: las estructuras de paquetes de Java,
por ejemplo, deben reflejar la estructura de directorios de los
archivos de clase físicos.

74UN LENGUAJE SIN CONFLICTOS DE NOMBRES: JAVA
1.0

Los diseñadores originales de Java tenían una amplia experiencia
lidiando con conflictos y choques de nombres, que eran comunes
en las plataformas de programación de la época. Java 1.0 utilizó
un truco ingenioso para evitar la ambigüedad cuando dos clases
tenían el mismo nombre; por ejemplo, si el dominio del problema
incluía un order (pedido) de catálogo y una order (orden) de
instalación, ambos llamados order pero con connotaciones (y
clases) muy diferentes. La solución de los diseñadores de Java
fue crear el mecanismo de espacio de nombres package, junto
con el requisito de que la estructura física de directorios debe
coincidir con el nombre del paquete. Debido a que los sistemas
de archivos no permiten que dos archivos con el mismo nombre
residan en el mismo directorio, esto aprovechó las características
inherentes del sistema operativo para evitar la ambigüedad y los
conflictos de nombres. Así, el classpath original en Java
contenía solo directorios.

Sin embargo, como descubrieron los diseñadores del lenguaje,
obligar a cada proyecto a tener una estructura de directorios
completamente formada era engorroso, especialmente a medida
que los proyectos se volvían más grandes. Además, construir
activos reutilizables era difícil: los frameworks y las bibliotecas
tenían que ser "explotados" en la estructura de directorios. En la
segunda versión importante de Java (1.2, pero llamada Java 2),
los diseñadores añadieron el mecanismo jar, que permite que
un archivo de biblioteca actúe como una estructura de directorios
en un classpath. Durante la década siguiente, los desarrolladores
de Java lucharon por configurar el classpath exactamente de la
manera correcta, como una combinación de directorios y
archivos JAR. Su intención original se había roto: ahora dos
archivos JAR podían crear nombres conflictivos en un classpath.

75Esta es la razón por la que los desarrolladores de Java de esa
época suelen tener numerosas historias de batalla sobre la
depuración de cargadores de clases (class loaders).

Midiendo la modularidad

Dado que la modularidad es tan importante, los arquitectos
necesitan herramientas que los ayuden a comprenderla mejor.
Afortunadamente, los investigadores han creado una variedad de
métricas independientes del lenguaje para este propósito. Aquí nos
centraremos en tres conceptos clave: cohesión, acoplamiento y
connascencia.

Cohesión

La cohesión se refiere al grado en que las partes de un módulo
deben estar contenidas dentro del mismo módulo. En otras palabras,
mide qué tan relacionadas están las partes entre sí. Un módulo
cohesivo ideal es aquel en el que todas las partes están
empaquetadas juntas; separarlas en piezas más pequeñas requeriría
acoplar las partes mediante llamadas entre módulos para lograr
resultados útiles. La moraleja de la modularidad en lo que respecta a
la cohesión se ejemplifica en la siguiente cita del libro Diseño
Estructurado (Pearson, 2008):

Intentar dividir un módulo cohesivo solo resultaría en un mayor
acoplamiento y una menor legibilidad.

—Larry Constantine

Los científicos de la computación han definido un rango de cohesión,
medido de mejor a peor:

Cohesión funcional

76Cada parte del módulo está relacionada con las demás, y el
módulo contiene todo lo esencial que necesita para
funcionar.

Cohesión secuencial

Dos módulos interactúan: uno produce datos de salida que
se convierten en la entrada para el otro.

Cohesión comunicacional

Dos módulos forman una cadena de comunicación en la que
cada uno opera sobre información y/o contribuye a alguna
salida. Por ejemplo, uno añade un registro a la base de datos
y el otro genera un correo electrónico basado en esa
información.

Cohesión procedimental

Dos módulos deben ejecutar código en un orden particular.

Cohesión temporal

Los módulos están relacionados basándose en dependencias
de tiempo. Por ejemplo, muchos sistemas tienen una lista de
cosas aparentemente no relacionadas que deben
inicializarse al arrancar el sistema; estas diferentes tareas
son temporalmente cohesivas.

Cohesión lógica

Los datos dentro de los módulos están relacionados
lógicamente pero no funcionalmente. Por ejemplo, considera
un módulo que convierte información de texto, objetos
serializados o ﬂujos de datos a algún otro formato. Sus
operaciones están relacionadas, pero las funciones son
bastante diferentes. Un ejemplo común de este tipo de
cohesión existe en prácticamente todos los proyectos de Java

77en la forma del paquete StringUtils, un grupo de métodos
estáticos que operan sobre String pero que, por lo demás, no
están relacionados.

Cohesión coincidente

Los elementos en un módulo no están relacionados más allá
de estar en el mismo archivo fuente. Esto representa la
forma más negativa de cohesión.

A pesar de sus muchas variantes, la cohesión es una métrica menos
precisa que el acoplamiento. A menudo, el grado de cohesión de un
módulo en particular se determina a discreción de un arquitecto
específico. Considera esta definición de módulo:

Mantenimiento de Clientes (Customer Maintenance)

add customer (añadir cliente)

update customer (actualizar cliente)

get customer (obtener cliente)

notify customer (notificar cliente)

get customer orders (obtener pedidos del cliente)

cancel customer orders (cancelar pedidos del cliente)

¿Deberían las dos últimas entradas residir en este módulo? ¿O
debería el desarrollador crear dos módulos separados? Así es como
se vería eso:

Customer Maintenance

78add customer (añadir cliente)

update customer (actualizar cliente)

get customer (obtener cliente)

notify customer (notificar cliente)

Mantenimiento de Pedidos (Order Maintenance)

get customer orders (obtener pedidos del cliente)

cancel customer orders (cancelar pedidos del cliente)

¿Cuál es la estructura correcta? Como siempre, depende:

¿Son estas las únicas dos operaciones para Order
Maintenance (mantenimiento de pedidos)? Si es así, puede
tener sentido volver a integrar esas operaciones en Customer
Maintenance (mantenimiento de clientes).

¿Se espera que Customer Maintenance (mantenimiento de
clientes) crezca mucho más? Si es así, quizás los
desarrolladores deberían buscar oportunidades para extraer
el comportamiento hacia un módulo diferente (o nuevo).

¿Requiere Order Maintenance (mantenimiento de pedidos)
tanto conocimiento de la información del Customer
(cliente) que separar los dos módulos requeriría un alto
grado de acoplamiento para hacerlo funcional? (Esto se
relaciona con la cita anterior de Larry Constantine).

Estas preguntas representan el tipo de análisis de compensaciones
que constituye el núcleo del trabajo de un arquitecto de software.

79Los científicos de la computación han desarrollado una buena
métrica estructural para determinar la cohesión; específicamente, la
Falta de Cohesión (Lack of Cohesion) (lo cual es un poco
sorprendente, dado lo subjetiva que es esta característica). Un
conjunto de métricas muy conocido llamado Chidamber and Kemerer
Object-Oriented Metrics Suite mide aspectos particulares de los
sistemas de software orientados a objetos. Incluye muchas métricas
de código comunes, como la Complejidad Ciclomática (ver
“Cyclomatic Complexity”) y varias métricas de acoplamiento
importantes, analizadas en “Coupling”.

Chidamber y Kemerer también han desarrollado una métrica de Falta
de Cohesión en los Métodos (LCOM, por sus siglas en inglés), que
mide la cohesión estructural de un módulo. La versión inicial aparece
en la Ecuación 3-1.

Ecuación 3-1. LCOM, versión 1

LCOM = {

|P | − |Q|,
0,

si |P | > |Q|
de lo contrario

)

En esta ecuación, P aumenta en 1 por cada método que no accede a
un campo compartido en particular; Q disminuye en 1 por los
métodos que sí comparten un campo compartido en particular. Si
esta formulación te parece confusa, te entendemos; y gradualmente
se ha vuelto aún más elaborada. La segunda variación, introducida
en 1996 (de ahí el nombre LCOM96B), aparece en la Ecuación 3-2.

Ecuación 3-2. LCOM96B

LCOM96b =

1
a

a
∑
j=1

m − μ(Aj)
m

80No nos molestaremos en desentrañar las variables y operadores de
la Ecuación 3-2 porque la siguiente explicación escrita es más clara.
Básicamente, la métrica LCOM expone el acoplamiento incidental
dentro de las clases. Una mejor definición de LCOM sería "la suma
de conjuntos de métodos que no se comparten a través de campos
compartidos".
Considera una clase con campos privados a y b. Muchos de los
métodos solo acceden a a, y muchos otros métodos solo acceden a
b. La suma de los conjuntos de métodos no compartidos a través de
campos compartidos (a y b) es alta; por lo tanto, esta clase incurre
en una puntuación LCOM alta, lo que indica una significativa falta de
cohesión en los métodos.

Considera las tres clases que se muestran en la Figura 3-1. Aquí, los
campos aparecen como letras individuales dentro de octágonos, y
los métodos aparecen como bloques. En la Clase X, la puntuación
LCOM es baja, lo que indica una buena cohesión estructural. La
Clase Y, sin embargo, carece de cohesión; cada uno de los pares
campo/método en la Clase Y podría aparecer en su propia clase sin
afectar el comportamiento del sistema. La Clase Z muestra una
cohesión mixta; la última combinación de campo/método podría ser
refactorizada en su propia clase.

81Esta ilustración representa la métrica de falta de cohesión en los métodos a través

de tres ejemplos denominados Clase X, Clase Y y Clase Z. En cada diagrama, los

octágonos  etiquetados  con  las  letras  A,  B  y  C  representan  los  campos  de  datos,

mientras que los cuadrados identificados como m1, m2 y m3 corresponden a los

métodos.  En  la  Clase  X,  se  observa  una  alta  interconexión  entre  campos  y

métodos, lo que indica una buena cohesión estructural. Por el contrario, la Clase Y

muestra conexiones aisladas por pares individuales, lo que sugiere una clara falta

de  cohesión,  ya  que  cada  conjunto  de  campo  y  método  podría  existir  de  forma

independiente. Finalmente, la Clase Z presenta una cohesión mixta donde algunos

elementos  están  vinculados  entre  sí,  mientras  que  el  campo  C  y  el  método  m3

aparecen  totalmente  desconectados  del  resto,  señalando  que  esa  parte  podría

refactorizarse en una clase distinta. (Accesibilidad de la imagen)

Figura 3-1. La métrica LCOM, donde los campos son octágonos y los métodos son
cuadrados

La métrica LCOM es útil para los arquitectos que están analizando
bases de código con el fin de ayudar en la reestructuración,
migración o comprensión de una base de código. Las clases de
utilidad compartidas son un dolor de cabeza común al mover
arquitecturas. El uso de la métrica LCOM puede ayudar a los
arquitectos a encontrar clases que están acopladas incidentalmente
y que nunca debieron haber sido una sola clase en primer lugar.

82Muchas métricas de software tienen deficiencias graves, y LCOM no
es inmune. Todo lo que esta métrica puede encontrar es la falta de
cohesión estructural; no tiene forma de determinar si piezas
particulares encajan lógicamente. Esto nos remite a nuestra
Segunda Ley de la Arquitectura de Software: el porqué es más
importante que el cómo.

Acoplamiento

Afortunadamente, tenemos mejores herramientas para analizar el
acoplamiento en las bases de código. Estas se basan en parte en la
teoría de grafos: debido a que las llamadas y retornos de métodos
forman un grafo de llamadas, este puede analizarse
matemáticamente. El libro de Edward Yourdon y Larry Constantine
Structured Design: Fundamentals of a Discipline of Computer
Program and Systems Design (Prentice-Hall, 1979), definió muchos
conceptos fundamentales, incluyendo las métricas de acoplamiento
aferente y acoplamiento eferente. El acoplamiento aferente mide el
número de conexiones entrantes a un artefacto de código
(componente, clase, función, etc.). El acoplamiento eferente mide
las conexiones salientes hacia otros artefactos de código. Existen
herramientas para prácticamente todas las plataformas que permiten
a los arquitectos analizar las características de acoplamiento del
código.

83¿POR QUÉ NOMBRES TAN SIMILARES PARA LAS
MÉTRICAS DE ACOPLAMIENTO?

¿Por qué dos métricas críticas en el mundo de la arquitectura
que representan conceptos opuestos se llaman prácticamente
igual, diferenciándose solo en las vocales que suenan más
parecido? Estos términos provienen del libro Structured Design.
Tomando prestados conceptos de las matemáticas, Yourdon y
Constantine acuñaron los términos ahora comunes de
acoplamiento aferente y eferente. Realmente deberían haberse
llamado acoplamiento entrante y saliente, pero los autores se
inclinaron por la simetría matemática en lugar de la claridad. Los
desarrolladores han ideado varias reglas mnemotécnicas para
ayudarse. Por ejemplo, la a aparece antes que la e en el
alfabeto, tal como entrante (incoming) aparece antes que
saliente (outgoing). La letra e en eferente coincide con la letra
inicial de exit (salida), lo que ayuda a recordar que representa
las conexiones salientes.

Métricas principales

Aunque el acoplamiento de componentes tiene un valor bruto para
los arquitectos, varias otras métricas derivadas permiten una
evaluación más profunda. Las métricas analizadas en esta sección
fueron creadas por el ingeniero de software Robert C. Martin, y se
aplican ampliamente a la mayoría de los lenguajes orientados a
objetos.

La Abstracción (Abstractness) es la relación entre los artefactos
abstractos (clases abstractas, interfaces, etc.) y los artefactos
concretos (implementaciones). La métrica de Abstracción mide el
grado de abstracción de una base de código frente a la
implementación. Por ejemplo, en un extremo de la escala estaría
una base de código sin abstracciones, solo una función de código

84enorme y única (como en un solo método main()). El otro extremo
de la escala sería una base de código con demasiadas abstracciones,
lo que dificultaría a los desarrolladores entender cómo se conectan
las cosas. (Por ejemplo, a los desarrolladores les toma un tiempo
descubrir qué hacer con una clase abstracta
AbstractSingletonProxyFactoryBean, dadas sus muchas capas de
abstracción y su nombre ambiguo).

La fórmula para la Abstracción aparece en la Ecuación 3-3.

Ecuación 3-3. Abstracción

A =

∑ ma
∑ mc + ∑ ma

Los arquitectos calculan la Abstracción calculando la proporción de la
suma de los artefactos abstractos respecto a la suma de los
concretos y abstractos. En la ecuación, ma
 representa los elementos
abstractos (interfaces o clases abstractas) dentro del módulo, y mc
representa los elementos concretos (clases no abstractas). Esta
métrica busca los mismos criterios. La forma más fácil de visualizar
esta métrica es considerar una aplicación con 5,000 líneas de código,
todas en un único método main() (principal). Su numerador de
Abstracción sería 1, mientras que el denominador sería 5,000, lo que
daría una puntuación de Abstracción de casi 0. Así es como esta
métrica mide la proporción de abstracciones en el código.

Otra métrica derivada, la Inestabilidad (Instability), se define como
la proporción del acoplamiento eferente respecto a la suma del
acoplamiento eferente y el aferente, como se muestra en la Ecuación
3-4.

85Ecuación 3-4. Inestabilidad

I =

C e
C e + C a

 representa el acoplamiento eferente (o saliente),

 representa el acoplamiento aferente (o entrante).

En la ecuación, ce
y ca
La métrica de Inestabilidad determina la volatilidad de una base de
código. Una base de código que exhibe altos grados de inestabilidad
se rompe más fácilmente cuando se modifica debido al alto
acoplamiento. Por ejemplo, si una clase llama a demasiadas otras
clases para delegar el trabajo, la clase que llama mostrará una alta
susceptibilidad a romperse si uno o más de los métodos llamados
cambian.

Distancia de la secuencia principal

Una de las pocas métricas holísticas que tienen los arquitectos para
la estructura arquitectónica es la Distancia de la Secuencia Principal
(Distance from the Main Sequence), una métrica derivada basada en
la Inestabilidad y la Abstracción, que se muestra en la Ecuación 3-5.

Ecuación 3-5. Distancia de la secuencia principal

D = |A + I − 1|

En la ecuación, A = Abstracción e I = Inestabilidad.

Ten en cuenta que tanto la Abstracción como la Inestabilidad son
fracciones cuyos resultados siempre estarán entre 0 y 1 (excepto en
algunos casos extremos). Por lo tanto, graficar la relación produce el
gráfico de la Figura 3-2.

86Este  gráfico  ilustra  la  relación  entre  la  abstracción  y  la  inestabilidad  de  los

componentes  en  una  arquitectura  de  software.  El  eje  vertical  representa  la

Abstracción (A) y el eje horizontal mide la Inestabilidad (I), ambos en una escala

que  llega  hasta  el  valor  uno.  Una  línea  diagonal  descendente,  denominada

Secuencia principal, conecta el punto máximo de abstracción con el punto máximo

de inestabilidad, definiendo el equilibrio ideal entre estas dos métricas para lograr

un diseño estructural saludable. (Accesibilidad de la imagen)

Figura 3-2. La secuencia principal define la relación ideal entre Abstracción e
Inestabilidad

La métrica de Distancia imagina una relación ideal entre la
Abstracción y la Inestabilidad; las clases que caen cerca de esta
línea idealizada exhiben una mezcla saludable de estos dos intereses
contrapuestos. Por ejemplo, graficar una clase en particular permite
a los desarrolladores calcular la métrica de Distancia de la Secuencia
Principal, ilustrada en la Figura 3-3.

87Este  gráfico  de  visualización  de  datos  representa  la  métrica  de  la  distancia  de  la

secuencia  principal,  la  cual  evalúa  el  equilibrio  entre  la  abstracción  (A)  en  el  eje

vertical y la inestabilidad (I) en el eje horizontal, ambos medidos en una escala de

cero  a  uno.  Una  línea  diagonal  descendente  identifica  la  secuencia  principal,  que

es  la  trayectoria  ideal  donde  los  componentes  mantienen  una  relación  saludable

entre  su  nivel  de  abstracción  y  su  estabilidad.  El  gráfico  muestra  un  punto  azul

que representa un artefacto de código específico y señala con una línea punteada

roja  su  distancia  de  la  secuencia  principal,  etiquetada  como  D,  lo  que  sirve  para

interpretar  qué  tan  alejado  se  encuentra  un  módulo  de  su  estado  óptimo  de

diseño. (Accesibilidad de la imagen)

Figura 3-3. Distancia normalizada de la secuencia principal para una clase en
particular

La métrica de la Figura 3-3 grafica la clase candidata y luego mide
su distancia respecto a la línea idealizada. Cuanto más cerca de la
línea, mejor equilibrada está la clase. Las clases que caen demasiado
hacia la esquina superior derecha entran en lo que los arquitectos
llaman la Zona de Inutilidad (Zone of Uselessness): el código que es
demasiado abstracto se vuelve difícil de usar. Por el contrario, el
código que cae en la esquina inferior izquierda, como se ilustra en la
Figura 3-4, entra en la Zona de Dolor (Zone of Pain): el código con

88demasiada implementación y poca abstracción se vuelve frágil y
difícil de mantener.

Este  gráfico  representa  la  relación  entre  la  Abstracción  (A)  y  la  Inestabilidad  (I)

para evaluar la estructura arquitectónica. En el eje vertical se mide la Abstracción,

mientras que en el eje horizontal se sitúa la Inestabilidad. El diagrama identifica la

Zona  de  dolor  en  la  parte  inferior  izquierda,  caracterizada  por  código  con  mucha

implementación  y  poca  abstracción  que  resulta  difícil  de  mantener,  y  la  Zona  de

inutilidad en la parte superior derecha, donde un exceso de abstracción dificulta su

uso  práctico.  La  franja  diagonal  verde  marca  la  secuencia  principal,  indicando  el

equilibrio  ideal  que  debes  buscar  para  que  tus  componentes  sean  saludables  y

fáciles  de  gestionar,  evitando  los  extremos  problemáticos.  (Accesibilidad  de  la

imagen)

Figura 3-4. Las zonas de inutilidad y de dolor

Muchas plataformas ofrecen herramientas para calcular estas
medidas, las cuales ayudan a los arquitectos cuando analizan bases
de código para familiarizarse con ellas, prepararse para una
migración o evaluar la deuda técnica.

89LAS LIMITACIONES DE LAS MÉTRICAS

Si bien la industria cuenta con algunas métricas a nivel de código
que proporcionan información valiosa, nuestras herramientas son
extremadamente toscas en comparación con las herramientas de
análisis de otras disciplinas de ingeniería. Incluso las métricas
derivadas directamente de la estructura del código requieren
interpretación. Por ejemplo, la Complejidad Ciclomática (ver
“Complejidad Ciclomática”) mide la complejidad en las bases de
código, pero esta métrica no puede distinguir entre la
complejidad esencial (el código es complejo porque el problema
subyacente es complejo) y la complejidad accidental (el código
es más complejo de lo que debería ser). Prácticamente todas las
métricas a nivel de código requieren interpretación, pero sigue
siendo útil establecer líneas base para métricas críticas como la
Complejidad Ciclomática, de modo que los arquitectos puedan
evaluar qué tipo exhibe la base de código. Discutiremos la
configuración de tales pruebas en “Gobernanza y funciones de
aptitud”.

Structured Design de Yourdon y Constantine, publicado en 1979, es
anterior a la popularidad de los lenguajes orientados a objetos. En
su lugar, se centra en constructos de programación estructurada,
como funciones (no métodos). También define otros tipos de
acoplamiento que están obsoletos debido al diseño de los lenguajes
de programación modernos. La programación orientada a objetos
introdujo conceptos adicionales que se superponen al acoplamiento
aferente y eferente, incluyendo un vocabulario más refinado para
describir el acoplamiento llamado connascence (conascencia).

Conascencia (Connascence)

El libro de Meilir Page-Jones What Every Programmer Should Know
about Object-Oriented Design (Dorset House, 1996) creó un

90lenguaje más preciso para describir diferentes tipos de acoplamiento
en lenguajes orientados a objetos. La conascencia no es una métrica
de acoplamiento como el acoplamiento aferente y eferente; más
bien, representa un lenguaje que ayuda a los arquitectos a describir
diferentes tipos de acoplamiento con mayor precisión (y a
comprender algunas consecuencias comunes de los tipos de
acoplamiento).

Dos componentes son conascentes si un cambio en uno requeriría
que el otro fuera modificado para mantener la corrección general del
sistema. Page-Jones distingue dos tipos de conascencia: estática y
dinámica.

Conascencia estática

La conascencia estática se refiere al acoplamiento a nivel de código
fuente (a diferencia del acoplamiento en tiempo de ejecución,
tratado en “Conascencia dinámica”). Los arquitectos ven la
conascencia estática como el grado en el que algo está acoplado a
través del acoplamiento aferente o eferente. Existen varios tipos de
conascencia estática:

Conascencia de Nombre

Múltiples componentes deben estar de acuerdo en el
nombre de una entidad.

Los nombres de los métodos y los parámetros de los métodos
son la forma más común en que las bases de código están
acopladas y la más deseable, especialmente a la luz de las
herramientas de refactorización modernas que hacen que
los cambios de nombre en todo el sistema sean triviales de
implementar. Por ejemplo, los desarrolladores ya no
cambian el nombre de un método en una base de código
activa, sino que refactorizan el nombre del método
utilizando herramientas modernas, afectando el cambio en
toda la base de código.

91Conascencia de Tipo

Múltiples componentes deben estar de acuerdo en el tipo de
una entidad.

Este tipo de conascencia se reﬁere a la tendencia común en
muchos lenguajes de tipado estático de limitar las variables
y los parámetros a tipos especíﬁcos. Sin embargo, esta
capacidad no es puramente para los lenguajes de tipado
estático; algunos lenguajes de tipado dinámico también
ofrecen tipado selectivo, notablemente Clojure y Clojure
Spec.

Conascencia de Significado

Múltiples componentes deben estar de acuerdo en el
signiﬁcado de valores particulares. También se le llama
Conascencia de Convención.

El caso obvio más común para este tipo de conascencia en
las bases de código son los números preﬁjados (hardcoded)
en lugar de las constantes. Por ejemplo, es común en algunos
lenguajes considerar deﬁnir en algún lugar que int TRUE =
1; int FALSE = 0. Imagina los problemas que surgirían si
alguien invirtiera esos valores.

Conascencia de Posición

Múltiples componentes deben estar de acuerdo en el orden
de los valores.

Este es un problema con los valores de los parámetros para
las llamadas a métodos y funciones, incluso en lenguajes que
cuentan con tipado estático. Por ejemplo, si un desarrollador
crea un método void updateSeat(String name, String
seatLocation) y lo llama con los valores updateSeat("14D",

92"Ford, N"), la semántica no es correcta, aunque los tipos sí lo
sean.

Conascencia de Algoritmo

Múltiples componentes deben estar de acuerdo en un
algoritmo particular.

Un caso común de Conascencia de Algoritmo ocurre cuando
un desarrollador deﬁne un algoritmo de hash de seguridad
que debe ejecutarse y producir resultados idénticos tanto en
el servidor como en el cliente para autenticar al usuario.
Obviamente, esto representa un alto grado de acoplamiento:
si cambian los detalles de cualquiera de los algoritmos, el
saludo (handshake) ya no funcionará.

Conascencia dinámica

El otro tipo de conascencia que define Page-Jones es la conascencia
dinámica, que analiza las llamadas en tiempo de ejecución. Los tipos
de conascencia dinámica incluyen:

Conascencia de Ejecución

El orden de ejecución de múltiples componentes es
importante.

Considera este código:

email = new Email();

email.setRecipient("foo@example.com");

email.setSender("me@me.com");

email.send();

email.setSubject("whoops");

No funcionará correctamente porque ciertas propiedades
deben establecerse en un orden especíﬁco.

93Conascencia de Temporización

El momento de la ejecución de múltiples componentes es
importante.

El caso común para este tipo de conascencia es una
condición de carrera causada por dos hilos que se ejecutan
al mismo tiempo, afectando el resultado de la operación
conjunta.

Conascencia de Valores

Varios valores dependen unos de otros y deben cambiar
juntos.

Considera un caso en el que un desarrollador ha deﬁnido un
rectángulo deﬁniendo cuatro puntos para representar sus
esquinas. Para mantener la integridad de la estructura de
datos, el desarrollador no puede cambiar aleatoriamente
uno de los puntos sin considerar el impacto en los otros
puntos para preservar la forma del rectángulo.

Un caso más común y problemático involucra transacciones,
especialmente en sistemas distribuidos. En un sistema
diseñado con bases de datos separadas, cuando alguien
necesita actualizar un solo valor en todas las bases de datos,
los valores deben cambiar todos juntos o no cambiar en
absoluto.

Conascencia de Identidad

Múltiples componentes deben hacer referencia a la misma
entidad.

Un ejemplo común de Conascencia de Identidad involucra
dos componentes independientes que deben compartir y
actualizar una estructura de datos común, como una cola
distribuida.

94Propiedades de la conascencia

La conascencia es un marco de análisis para arquitectos y
desarrolladores, y algunas de sus propiedades ayudan a asegurar
que lo usemos sabiamente. Estas propiedades de la conascencia
incluyen:

Fuerza

Los arquitectos determinan la fuerza (strength) de la
conascencia de un sistema por la facilidad con la que un
desarrollador puede refactorizar su acoplamiento. Algunos
tipos de conascencia son demostrablemente más deseables
que otros, como se muestra en la Figura 3-5. Refactorizar
hacia mejores tipos de conascencia puede mejorar las
características de acoplamiento de una base de código.

Los arquitectos deberían preferir la conascencia estática a la
dinámica porque los desarrolladores pueden determinarla
mediante un simple análisis del código fuente, y porque las
herramientas modernas hacen que mejorar la conascencia
estática sea trivial. Por ejemplo, la Conascencia de Signiﬁcado
podría mejorarse refactorizando a Conascencia de Nombre,
creando una constante con nombre en lugar de un valor
mágico.

95Esta  visualización  técnica  ilustra  la  jerarquía  de  la  conascedencia  en  el  desarrollo

de software, indicando que debes refactorizar en esta dirección, es decir, desde los

niveles más complejos hacia los más simples y preferibles. El gráfico clasifica estos

conceptos  en  dos  grandes  grupos:  la  categoría  estática,  que  comprende  los

elementos  de  nombre,  tipo,  significado,  algoritmo  y  posición;  y  la  categoría

dinámica, que abarca la ejecución, temporización, valor e identidad. La flecha con

gradiente  de  color,  que  asciende  desde  el  rojo  hacia  el  verde,  sugiere  que

transformes los acoplamientos dinámicos en estáticos para mejorar la calidad y la

mantenibilidad del código. (Accesibilidad de la imagen)

Figura 3-5. La fuerza de la conascencia puede ser una buena guía de
refactorización

Localidad

La localidad de la conascencia de un sistema mide qué tan
proximales (cercanos) son sus módulos entre sí en la base de
código. El código proximal (código en el mismo módulo)
normalmente tiene formas de conascencia más numerosas y
elevadas que el código más separado (en módulos o bases de
código distintos). En otras palabras, las formas de

96conascencia que indicarían un acoplamiento deﬁciente
cuando los componentes están lejos, están bien cuando los
componentes están más cerca. Por ejemplo, si dos clases en
el mismo módulo tienen Conascencia de Signiﬁcado, es
menos perjudicial para la base de código que si esas clases
estuvieran en módulos diferentes.

Los arquitectos no eran muy conscientes de la importancia
de esta observación cuando el autor la publicó por primera
vez. En términos modernos, sugiere que los arquitectos
deberían limitar el alcance de los detalles de
implementación (alto acoplamiento) tanto como sea
práctico, que es el mismo consejo derivado de la idea del
contexto delimitado (bounded context) del diseño guiado
por el dominio (DDD). La observación arquitectónica es la
misma: limitar el acoplamiento de implementación. Meilir
Page-Jones describió un buen principio de diseño que se
reintrodujo de forma más completa a través de DDD (ver
“Contexto delimitado del diseño guiado por el dominio” en el
Capítulo 7).

Es buena idea considerar la fuerza y la localidad juntas. Las
formas más fuertes de conascencia dentro del mismo
módulo representan menos "olor de código" (code smell) que
la misma conascencia dispersa.

Grado

El grado de conascencia se relaciona con la magnitud del
impacto de cambiar una clase en un módulo en particular:
¿ese cambio afecta a unas pocas clases o a muchas? Menores
grados de conascencia requieren menos cambios en otras
clases y módulos y, por lo tanto, dañan menos las bases de
código. En otras palabras, tener una alta conascencia
dinámica no es terrible si un arquitecto solo tiene unos
pocos módulos. Sin embargo, las bases de código tienden a

97crecer, lo que hace que un problema pequeño sea
proporcionalmente más grande en términos de cambio.

En What Every Programmer Should Know about Object-Oriented
Design, Page-Jones ofrece tres pautas para usar la conascencia con
el fin de mejorar la modularidad del sistema:

Minimiza la conascencia general dividiendo el sistema en
elementos encapsulados.

Minimiza cualquier conascencia restante que cruce los límites
de encapsulación.

Maximiza la conascencia dentro de los límites de
encapsulación.

El legendario innovador de la arquitectura de software Jim Weirich,
quien repopularizó el concepto de conascencia, ofrece dos grandes
reglas en su charla sobre “Connescence Examined” durante la
conferencia Emerging Technologies for the Enterprise en 2012:

Regla del Grado: Convierte las formas fuertes de conascencia en
formas más débiles de conascencia.

Regla de la Localidad: A medida que aumenta la distancia entre
los elementos de software, utiliza formas más débiles de
conascencia.

Los arquitectos se benefician al aprender sobre la conascencia por la
misma razón que es beneficioso aprender sobre los patrones de
diseño: la conascencia proporciona un lenguaje más preciso para
describir diferentes tipos de acoplamiento. Por ejemplo, un
arquitecto puede decirle a alguien: "Necesitamos un servicio y solo
puede haber una instancia", o puede decirle: "Necesitamos un
servicio Singleton". El patrón de diseño Singleton encapsula muy
bien el contexto y la solución a un problema común con un nombre
sencillo.

98De manera similar, al realizar una revisión de código, un arquitecto
puede instruir a un desarrollador: "No añadas una constante de
cadena mágica en medio de la declaración de un método. Extráela
como una constante en su lugar". O podría decir: "Tienes
Conascencia de Significado; refactorízala a Conascencia de Nombre."

De los módulos a los componentes

Usamos el término módulo a lo largo de este libro como un nombre
genérico para conjuntos de código relacionado. Sin embargo, la
mayoría de los arquitectos se refieren a los módulos como
componentes, los bloques de construcción clave para la arquitectura
de software. Este concepto de componente, y el correspondiente
análisis de la separación lógica o física, ha existido desde los inicios
de la informática, y aun así, los desarrolladores y arquitectos todavía
luchan por lograr buenos resultados.

Hablaremos sobre cómo derivar componentes a partir de dominios
de problemas en el Capítulo 8, pero primero debemos discutir otro
aspecto fundamental de la arquitectura de software: las
características arquitectónicas y su alcance.


148Capítulo 6. Medición y
gobernanza de las
características de la
arquitectura

Los arquitectos deben lidiar con una variedad extraordinariamente
amplia de características de arquitectura en todos los diferentes
aspectos de los proyectos de software. Los aspectos operativos
como el rendimiento, la elasticidad y la escalabilidad se mezclan con
las preocupaciones estructurales, como la modularidad y la facilidad
de despliegue. A los arquitectos les beneficia entender cómo medir y
gobernar las características arquitectónicas, en lugar de ahogarse en
términos ambiguos y definiciones amplias. Este capítulo se centra en
definir concretamente algunas de las características de arquitectura
más comunes y analiza cómo construir mecanismos de gobernanza
para ellas.

Medición de las características de la
arquitectura

A los arquitectos les cuesta definir las características arquitectónicas
por varias razones:

No son física

Muchas características de arquitectura de uso común tienen
signiﬁcados vagos. Por ejemplo, ¿cómo diseña un arquitecto
para la agilidad o la facilidad de despliegue? ¿Y qué hay de un
rendimiento extremadamente rápido? La gente de la industria
tiene perspectivas muy diferentes sobre términos comunes,

149a veces impulsadas por contextos legítimamente distintos y
otras veces de forma accidental.

Definiciones sumamente variables

Incluso dentro de una misma organización, diferentes
departamentos pueden no estar de acuerdo con las
deﬁniciones de características críticas como el rendimiento.
Hasta que los desarrolladores, arquitectos, operaciones y
demás puedan uniﬁcarse en una deﬁnición común, ¿cómo
podrán tener una conversación adecuada?

Demasiado compuestas

Muchas características de arquitectura deseables son en
realidad colecciones de otras características a menor escala,
como recordarás de nuestra discusión sobre las
características arquitectónicas compuestas en el Capítulo 5.
Por ejemplo, la agilidad se desglosa en características como
modularidad, facilidad de despliegue y testabilidad.

Descomponer las características arquitectónicas compuestas en sus
partes constitutivas es una parte importante para establecer
definiciones objetivas para las características de la arquitectura, lo
que resuelve estos tres problemas.

Cuando una organización acuerda que todos usarán definiciones
estándar y concretas para las características de la arquitectura,
crean un lenguaje ubicuo en torno a la arquitectura. Esta
estandarización les permite desglosar las características compuestas
para descubrir rasgos objetivamente medibles.

Medidas operativas

Muchas características de arquitectura tienen mediciones directas
obvias, como el rendimiento o la escalabilidad. Sin embargo, incluso

150estas ofrecen muchas interpretaciones matizadas, dependiendo de
los objetivos del equipo. Por ejemplo, tal vez tu equipo mida el
tiempo de respuesta promedio para ciertas solicitudes; un buen
ejemplo de una medida para una característica de arquitectura
operativa. Pero si tu equipo solo mide el promedio, ¿qué sucede si
alguna condición límite hace que el 1% de las solicitudes tarde 10
veces más que las demás? Si el sitio tiene suficiente tráfico, puede
que los valores atípicos ni siquiera aparezcan. Para detectar valores
atípicos, es posible que también quieras medir los tiempos de
respuesta máximos.

Los equipos de alto nivel no solo establecen números de rendimiento
rígidos; basan sus definiciones en el análisis estadístico. Por ejemplo,
supongamos que un servicio de streaming de video quiere
monitorear la escalabilidad. En lugar de establecer un número
arbitrario como objetivo, los ingenieros miden la escala a lo largo del
tiempo y construyen modelos estadísticos, para luego activar
alarmas si las métricas en tiempo real caen fuera de los modelos de
predicción. Si lo hacen, el fallo puede significar dos cosas: el modelo
es incorrecto (lo cual los equipos quieren saber) o algo anda mal (lo
cual los equipos también quieren saber).

Los tipos de características que los equipos miden evolucionan
rápidamente junto con las herramientas, los objetivos, los
dispositivos y las capacidades. Por ejemplo, recientemente muchos
equipos se han centrado en los presupuestos de rendimiento para
métricas como first contentful paint (primer despliegue de
contenido) y first CPU idle (primer tiempo de inactividad de la CPU),
las cuales dicen mucho sobre los problemas de rendimiento para los
usuarios de páginas web en dispositivos móviles. A medida que
estas y otras muchísimas cosas cambian, los equipos encontrarán
nuevas cosas y formas de medirlas.

151LOS MUCHOS SABORES DEL RENDIMIENTO

Muchas de las características de arquitectura que describimos
tienen múltiples definiciones. El rendimiento es un gran ejemplo.
Muchos proyectos observan el rendimiento general: por ejemplo,
cuánto duran los ciclos de solicitud y respuesta para una
aplicación web. Sin embargo, a través de un trabajo tremendo,
los arquitectos y los ingenieros de DevOps en muchas
organizaciones han establecido presupuestos de rendimiento
específicos para partes específicas de una aplicación. Por
ejemplo, muchas organizaciones han investigado el
comportamiento del usuario y determinado que el tiempo óptimo
para el renderizado de la primera página (la primera señal visible
de progreso de una página web en un navegador o dispositivo
móvil) es de una fracción de segundo. La mayoría de las
aplicaciones caen en el rango de dos dígitos para esta métrica.
Pero para los sitios modernos que intentan captar a tantos
usuarios como sea posible, esta es una métrica importante de
rastrear, y las organizaciones detrás de tales sitios han construido
medidas extremadamente matizadas.

Algunas de estas métricas tienen implicaciones adicionales para
el diseño de la aplicación. Muchas organizaciones con visión de
futuro establecen presupuestos de peso en kilobytes (K-weight
budgets) para las descargas de páginas; es decir, permiten una
cantidad máxima de bytes en bibliotecas y frameworks en una
página en particular. Su razonamiento deriva de las restricciones
físicas: solo una cantidad limitada de bytes puede viajar a través
de una red a la vez, especialmente para dispositivos móviles en
áreas de bajo ancho de banda.

152Medidas estructurales

Algunas medidas objetivas no son tan obvias como el rendimiento.
¿Qué pasa con las características estructurales internas, como una
modularidad bien definida? Este es un gran ejemplo de una
característica arquitectónica implícita: los arquitectos son
responsables de definir los componentes y las interacciones, y
quieren construir una estructura sostenible para una alta calidad
general. Desafortunadamente, todavía no existen métricas
exhaustivas para evaluar la calidad de una arquitectura. Sin
embargo, hay métricas y herramientas comunes que permiten a los
arquitectos abordar algunos aspectos críticos de la estructura del
código, aunque sea en dimensiones estrechas.

Un aspecto medible del código es la complejidad, definida por la
métrica de Complejidad ciclomática (Cyclomatic Complexity).

153COMPLEJIDAD CICLOMÁTICA

La Complejidad ciclomática (CC) es una métrica a nivel de código
diseñada por Thomas McCabe Sr. en 1976 para proporcionar una
medida objetiva de la complejidad del código a nivel de
función/método, clase o aplicación. Se calcula aplicando la teoría
de grafos al código, específicamente a los puntos de decisión,
que causan diferentes rutas de ejecución. Por ejemplo, si una
función no tiene sentencias de decisión (como las sentencias if),
entonces CC = 1. Si la función tiene una sola condicional,
entonces CC = 2 porque hay dos rutas de ejecución posibles.

La fórmula para calcular la CC para una sola función o método es
CC = E − N + 2, donde N (nodos) representa los nodos
(líneas de código), y E (aristas) representa las aristas (posibles
decisiones). Considera el código tipo C que se muestra en el
Ejemplo 6-1.

Ejemplo 6-1. Código de muestra para la evaluación de la
complejidad ciclomática
public void decision(int c1, int c2) {
    if (c1 < 100)
        return 0;
    else if (c1 + C2 > 500)
       return 1;
    else
      return -1;
}

La complejidad ciclomática para el Ejemplo 6-1 es 3 (3 – 2 + 2),
como se muestra en la Figura 6-1.

154Esta imagen ilustra un gráfico de complejidad ciclomática para una función de

decisión, donde se muestran diversos bloques de código interconectados que

representan  diferentes  rutas  de  ejecución.  En  la  parte  superior,  el  primer

cuadro  contiene  la  instrucción  "si  (c1  <  100)  retornar  0;",  seguido  de  una

transición hacia un segundo bloque que indica "de lo contrario, si (c1 + C2 >

500)".  Este  último  se  ramifica  hacia  dos  resultados  finales:  uno  que  dice

"retornar  -1;"  y  otro  marcado  como  "de  lo  contrario  retornar  1;".  La  imagen

incluye  etiquetas  explicativas  en  las  que  el  término  "Nodos"  señala  a  los

cuadros que contienen las líneas de código, mientras que la palabra "Aristas"

se  refiere  a  las  líneas  y  flechas  que  conectan  dichos  cuadros,  representando

las  posibles  decisiones  dentro  de  la  lógica  del  programa.  (Accesibilidad  de  la

imagen)

Figura 6-1. Gráfico de complejidad ciclomática para la función de decisión

El número 2 que aparece en la fórmula de complejidad
ciclomática representa una simplificación para una sola
función/método. Para las llamadas fan-out a otros métodos
(conocidas como componentes conectados en la teoría de
grafos), la fórmula más general es CC = E − N + 2P , donde
P representa el número de componentes conectados.

Los arquitectos y desarrolladores coinciden universalmente en que el
código excesivamente complejo representa un "code smell" (hedor
de código), algo que aparece en el código y que es tan malo que
tiene un olor imaginario. Perjudica prácticamente todas las

155características deseables de las bases de código: modularidad,
testabilidad, facilidad de despliegue, etc. Si los equipos no vigilan la
complejidad que crece gradualmente, esta dominará la base de
código.

La complejidad ciclomática es un gran ejemplo de lo toscas que son
las métricas que los arquitectos tienen a su disposición. Si bien mide
la complejidad del código, no puede determinar si esa complejidad
es esencial (porque estamos resolviendo un problema complicado) o
accidental (porque hemos implementado un diseño deficiente). Las
métricas como la CC son extremadamente útiles para evaluar el
código, ya sea escrito por desarrolladores o por IA generativa. La IA
generativa tiende a resolver problemas por fuerza bruta, lo que a
menudo conduce a una complejidad accidental.

156¿CUÁL ES UN BUEN VALOR PARA LA COMPLEJIDAD
CICLOMÁTICA?

Una pregunta común que los autores reciben cuando hablan
sobre este tema es: ¿cuál es un buen valor de umbral para la
CC? Por supuesto, como todas las preguntas en arquitectura de
software, la respuesta es: ¡depende! Específicamente, depende
de la complejidad del dominio del problema. Por ejemplo, si
tienes un problema algorítmicamente complejo, la solución
producirá funciones complejas. Algunos de los aspectos clave de
la CC que los arquitectos deben monitorear son: ¿son las
funciones complejas debido al dominio del problema o debido a
una mala codificación? Alternativamente, ¿está el código mal
particionado? En otras palabras, ¿podría un método grande
dividirse en trozos lógicos más pequeños, distribuyendo el
trabajo (y la complejidad) en métodos mejor factorizados?

En general, los umbrales de la industria para la CC sugieren que
un valor inferior a 10 es aceptable, salvo otras consideraciones
como dominios complejos. Nosotros consideramos que ese
umbral es muy alto y preferiríamos que el código bajara de cinco,
lo que indicaría un código cohesivo y bien factorizado. Una
herramienta de métricas en el mundo Java, Crap4J, intenta
determinar qué tan malo (cutre) es tu código evaluando una
combinación de CC y cobertura de código; si la CC crece a más
de 50, ninguna cantidad de cobertura de código rescata ese
código de la cutrez. ¡El artefacto profesional más aterrador que
Neal jamás encontró fue una sola función de C que servía como
el corazón de un paquete de software comercial cuya CC era
superior a 800! Era una sola función con más de 4,000 líneas de
código, incluyendo el uso liberal de sentencias GOTO (para
escapar de bucles anidados a una profundidad imposible).

Las prácticas de ingeniería como el desarrollo guiado por
pruebas (TDD) tienen el efecto secundario beneficioso de

157generar, en promedio, métodos más pequeños y menos
complejos para un dominio de problema dado. Al practicar TDD,
los desarrolladores intentan escribir una prueba simple y luego
escriben la menor cantidad de código para pasar la prueba. Este
enfoque en el comportamiento discreto y los buenos límites de
las pruebas fomenta métodos bien factorizados y altamente
cohesivos que exhiben una CC baja.

Medidas de proceso

Algunas características de la arquitectura se cruzan con los procesos
de desarrollo de software. Por ejemplo, la agilidad a menudo
aparece como una característica deseable. Sin embargo, es una
característica de arquitectura compuesta, formada por rasgos como
la testabilidad y la facilidad de despliegue.

La testabilidad es medible a través de herramientas de cobertura de
código para prácticamente todas las plataformas que informan sobre
qué porcentaje del código ejecutan las pruebas. Sin embargo, como
todas las comprobaciones de software, estas no pueden reemplazar
el pensamiento y la intención. Por ejemplo, una base de código
puede tener una cobertura del 100%, pero usar aserciones
deficientes que realmente no brindan confianza en la corrección del
código.

La testabilidad es una característica objetivamente medible, al igual
que la facilidad de despliegue. Las métricas de facilidad de
despliegue incluyen el porcentaje de despliegues exitosos, cuánto
tiempo duran los mismos y los problemas/errores generados por
ellos. Cada equipo debe llegar a un buen conjunto de mediciones
que capturen datos cualitativos y cuantitativos útiles para las
prioridades y objetivos de su organización y equipo.

Si bien la agilidad y sus partes relacionadas se relacionan claramente
con el proceso de desarrollo de software, ese proceso puede influir

158en la estructura de la arquitectura. Por ejemplo, si la facilidad de
despliegue y la testabilidad son prioridades altas, el arquitecto
enfatizaría una buena modularidad y aislamiento a nivel de
arquitectura; un ejemplo de una característica de arquitectura que
impulsa una decisión estructural. Prácticamente cualquier cosa
dentro del alcance de un proyecto de software puede elevarse al
nivel de una característica de arquitectura si logra cumplir con
nuestros tres criterios, obligando a un arquitecto a tomar decisiones
significativas para tenerla en cuenta.

Gobernanza y funciones de aptitud

Una vez que los arquitectos establecen y priorizan las características
de la arquitectura, ¿cómo pueden asegurarse de que los
desarrolladores respeten esas prioridades e implementen sus
diseños de manera correcta y segura, independientemente de la
presión del cronograma? En muchos proyectos de software, la
urgencia domina, pero los arquitectos aún necesitan herramientas y
técnicas para proporcionar gobernanza arquitectónica. La
modularidad es un gran ejemplo de un aspecto de la arquitectura
que es importante pero no urgente.

Gobernanza de las características de la
arquitectura

La Gobernanza, derivada de la palabra griega kubernan (dirigir), es
una responsabilidad importante del rol del arquitecto. Como su
nombre indica, su alcance cubre cualquier aspecto del proceso de
desarrollo de software en el que los arquitectos quieran influir. Por
ejemplo, garantizar la calidad del software cae bajo la gobernanza
arquitectónica porque descuidarla puede llevar a problemas de
calidad desastrosos.

159Afortunadamente, los arquitectos cuentan con soluciones cada vez
más sofisticadas para este problema, un buen ejemplo del
crecimiento incremental dentro de las capacidades del ecosistema de
desarrollo de software. El impulso hacia la automatización generado
por Extreme Programming creó la integración continua (CI). La CI
llevó a una mayor automatización en las operaciones, que ahora
llamamos DevOps, y esta cadena continúa hasta la gobernanza
arquitectónica. El libro Building Evolutionary Architectures (O’Reilly,
2022) de Neal Ford et al. describe una familia de técnicas llamadas
funciones de aptitud (fitness functions) utilizadas para automatizar
muchos aspectos de la gobernanza de la arquitectura. Pasaremos el
resto de este capítulo analizando las funciones de aptitud.

Funciones de aptitud

La palabra evolutionary (evolutiva) en el título Building Evolutionary
Architectures proviene más de la computación evolutiva que de la
biología. Una de las autoras, la Dra. Rebecca Parsons, pasó un
tiempo en el espacio de la computación evolutiva, incluyendo el
trabajo con herramientas como algoritmos genéticos. Cuando un
desarrollador diseña un algoritmo genético para producir algún
resultado beneficioso, a menudo quiere guiar el algoritmo
proporcionando una medida objetiva de la calidad de su resultado.
Ese mecanismo de guía se llama función de aptitud (fitness
function): una función de objeto utilizada para evaluar qué tan cerca
está la salida de lograr su objetivo.

Por ejemplo, supón que necesitas resolver el problema del vendedor
viajero, un problema famoso utilizado como base para el aprendizaje
automático. Dado un vendedor, una lista de ciudades que debe
visitar y las distancias entre esas ciudades, ¿cuál es la ruta óptima
posible (minimizando la distancia, el tiempo y el costo)? Si diseñas
un algoritmo genético para resolver este problema, podrías usar una
función de aptitud para evaluar la longitud de la ruta y otra para

160evaluar el costo total asociado con la ruta. Otra más podría evaluar
el tiempo que el vendedor viajero está fuera.

Las prácticas en arquitectura evolutiva toman prestado este
concepto para crear una función de aptitud arquitectónica: cualquier
mecanismo que proporcione una evaluación de integridad objetiva
de alguna característica de la arquitectura o combinación de
características de la arquitectura.

Las funciones de aptitud no son un nuevo framework que los
arquitectos deban descargar. Más bien, ofrecen una nueva
perspectiva sobre muchas herramientas existentes. Nota que en la
definición aparece la frase cualquier mecanismo: las técnicas de
verificación para las características de la arquitectura son tan
variadas como lo son las propias características. Las funciones de
aptitud se solapan con muchos mecanismos de verificación
existentes, dependiendo de la forma en que se utilicen: en la
ingeniería del caos o como métricas, monitores o librerías de
pruebas unitarias (ver Figura 6-2).

161La imagen presenta un diagrama compuesto por varios círculos de color azul claro

que se superponen entre sí para ilustrar los diversos mecanismos de las funciones

de aptitud. En el círculo central y de mayor tamaño se lee Funciones de aptitud, el

cual está rodeado por otros elementos que representan sus diferentes aplicaciones

y  herramientas:  Métricas  a  la  izquierda,  Monitores  en  la  parte  inferior  izquierda,

Pruebas unitarias en la parte inferior derecha e Ingeniería del caos a la derecha.

Finalmente, un círculo en la parte superior derecha contiene puntos suspensivos,

lo  que  sugiere  que  existen  otros  componentes  adicionales  que  también  forman

parte  de  este  ecosistema  de  verificación  arquitectónica.  (Accesibilidad  de  la

imagen)

Figura 6-2. Los mecanismos de las funciones de aptitud

Se pueden utilizar muchas herramientas diferentes para implementar
funciones de aptitud, dependiendo de las características de la
arquitectura. Veamos un par de ejemplos de funciones de aptitud
que prueban varios aspectos de la modularidad.

Dependencias cíclicas

La modularidad es una característica implícita de la arquitectura por
la que la mayoría de los arquitectos se preocupan. Debido a que una
modularidad mal mantenida perjudica la estructura de una base de
código, los arquitectos generalmente otorgan una alta prioridad a

162mantener una buena modularidad. Sin embargo, en muchas
plataformas, existen fuerzas que actúan en contra de esas buenas
intenciones. Por ejemplo, al codificar en cualquier entorno de
desarrollo popular de Java o .NET, tan pronto como un desarrollador
hace referencia a una clase que aún no ha sido importada, el IDE
presenta útilmente un diálogo preguntando si desea importar
automáticamente la referencia. Esto ocurre tan a menudo que la
mayoría de los programadores descartan por reflejo el diálogo de
importación automática. Pero importar clases arbitrariamente entre
componentes puede significar un desastre para la modularidad. Por
ejemplo, la Figura 6-3 ilustra las dependencias cíclicas, un antipatrón
particularmente dañino que los arquitectos aspiran a evitar.

En la Figura 6-3, cada componente hace referencia a algo en los
otros componentes. Tener una red como esta daña la modularidad,
porque es imposible reutilizar un solo componente sin traer a los
demás consigo. ¿Y si esos otros componentes están acoplados a
otros más? La arquitectura tenderá cada vez más hacia el antipatrón
de la Gran Bola de Lodo (Big Ball of Mud). ¿Cómo pueden los
arquitectos gobernar este comportamiento sin estar constantemente
vigilando a los desarrolladores? Las revisiones de código ayudan,
pero ocurren demasiado tarde en el ciclo de desarrollo para ser
totalmente efectivas. Si el equipo de desarrollo importa
desenfrenadamente por toda la base de código durante una semana
hasta la revisión de código, ya habrán causado un daño serio a la
base de código.

163Esta  ilustración  presenta  tres  bloques  tridimensionales  de  color  azul  claro,  cada

uno con la etiqueta código en su interior. Los bloques están organizados en forma

de triángulo y se conectan entre sí mediante flechas negras de doble punta, lo que

representa gráficamente la existencia de dependencias cíclicas o un acoplamiento

bidireccional  entre  los  distintos  módulos  de  programación.  (Accesibilidad  de  la

imagen)

Figura 6-3. Dependencias cíclicas entre componentes

La solución a este problema es escribir una función de aptitud para
vigilar los ciclos, como se muestra en el Ejemplo 6-2.

Ejemplo 6-2. Función de aptitud para detectar ciclos de
componentes
public class CycleTest {
    private JDepend jdepend;

    @BeforeEach
    void init() {
      jdepend = new JDepend();
      jdepend.addDirectory("/path/to/project/persistence/classes");
      jdepend.addDirectory("/path/to/project/web/classes");
      jdepend.addDirectory("/path/to/project/thirdpartyjars");
    }

    @Test
    void testAllPackages() {

164      Collection packages = jdepend.analyze();
      assertEquals("Cycles exist", false, jdepend.containsCycles());
    }
}

Este código utiliza la herramienta de métricas JDepend para
comprobar las dependencias entre paquetes. La herramienta
comprende la estructura de los paquetes Java y falla la prueba si
encuentra algún ciclo. Un arquitecto puede integrar esta prueba en
la construcción continua de un proyecto y dejar de preocuparse de
que los desarrolladores con "dedo rápido" introduzcan ciclos
accidentalmente. Este es un gran ejemplo de una función de aptitud
que protege las prácticas de desarrollo de software que son
importantes más que urgentes: es una preocupación importante
para los arquitectos, pero tiene poco impacto en la codificación
diaria.

Función de aptitud de distancia de la secuencia principal

En "Acoplamiento", presentamos la métrica más esotérica de la
Distancia de la secuencia principal, que también puede verificarse
mediante funciones de aptitud, como se muestra en el Ejemplo 6-3.

Ejemplo 6-3. Función de aptitud de distancia de la secuencia
principal
@Test
void AllPackages() {
    double ideal = 0.0;
    double tolerance = 0.5; // dependiente del proyecto
    Collection packages = jdepend.analyze();
    Iterator iter = packages.iterator();
    while (iter.hasNext()) {
      JavaPackage p = (JavaPackage)iter.next();
      assertEquals("Distancia excedida: " + p.getName(),
        ideal, p.distance(), tolerance);
    }
}

165Este código utiliza JDepend para establecer un umbral de valores
aceptables, fallando la prueba si una clase cae fuera del rango. (La
herramienta ArchUnit, destacada en la siguiente sección, permite a
los arquitectos crear funciones de aptitud similares). Este ejemplo de
una medida objetiva para una característica de la arquitectura ilustra
la importancia de la colaboración entre desarrolladores y arquitectos
al diseñar e implementar funciones de aptitud. La intención no es
que un grupo de arquitectos se encierre en una torre de marfil y
desarrolle funciones de aptitud esotéricas que los desarrolladores no
puedan entender; es implementar reglas de gobernanza
automatizadas que garanticen la calidad de la base de código.

CONSEJO

Los arquitectos deben asegurarse de que los desarrolladores
comprendan el propósito de una función de aptitud antes de
imponérsela.

La sofisticación de las herramientas de funciones de aptitud ha
aumentado en los últimos años, especialmente a medida que han
surgido algunas herramientas de propósito especial. Una de esas
herramientas es ArchUnit, un framework de pruebas de Java
inspirado en varias partes del ecosistema JUnit (y que las utiliza).
ArchUnit proporciona una variedad de reglas de gobernanza
predefinidas, codificadas como pruebas unitarias, y permite a los
arquitectos escribir pruebas específicas que aborden la modularidad.
Considera la arquitectura en capas ilustrada en la Figura 6-4.

166Esta ilustración muestra un diagrama de arquitectura por capas que representa la

estructura  interna  de  una  aplicación  y  su  interacción  con  el  almacenamiento  de

datos.  En  el  bloque  principal,  se  distinguen  cuatro  niveles  organizados  de  forma

jerárquica:  la  Presentación  en  la  parte  superior,  seguida  por  el  Controlador,  el

Servicio  y  la  Persistencia  en  la  base.  Este  conjunto  de  componentes  está

conectado mediante una flecha bidireccional a un cilindro que simboliza la Base de

datos, lo cual indica el flujo constante de información entre el sistema y su fuente

de almacenamiento. (Accesibilidad de la imagen)

Figura 6-4. Arquitectura en capas

Al diseñar un monolito en capas como el de la Figura 6-4, el
arquitecto define las capas por buenas razones (describimos estas
motivaciones, compensaciones y otros aspectos en el Capítulo 10).
Sin embargo, es posible que algunos desarrolladores no entiendan la
importancia de estos patrones, mientras que otros pueden adoptar
una actitud de "es mejor pedir perdón que permiso" debido a alguna
preocupación local predominante, como el rendimiento. Pero
permitirles erosionar los fundamentos de la arquitectura perjudicará
la salud a largo plazo de la misma.

167ArchUnit permite a los arquitectos abordar este problema a través de
una función de aptitud, que se muestra en el Ejemplo 6-4.

Ejemplo 6-4. Función de aptitud de ArchUnit para gobernar las capas
layeredArchitecture()
    .layer("Controller").definedBy("..controller..")
    .layer("Service").definedBy("..service..")
    .layer("Persistence").definedBy("..persistence..")

    .whereLayer("Controller").mayNotBeAccessedByAnyLayer()
    .whereLayer("Service").mayOnlyBeAccessedByLayers("Controller")
    .whereLayer("Persistence").mayOnlyBeAccessedByLayers("Service")

En el Ejemplo 6-4, el arquitecto define la relación deseable entre las
capas y escribe una función de aptitud de verificación para
gobernarla.

Existe una herramienta similar en el espacio de .NET, NetArchTest. El
Ejemplo 6-5 muestra una verificación de capas en C#.

Ejemplo 6-5. NetArchTest para dependencias de capas
// Las clases en la capa de presentación no deben hacer referencia
directa a los repositorios
var result = Types.InCurrentDomain()
    .That()
    .ResideInNamespace("NetArchTest.SampleLibrary.Presentation")
    .ShouldNot()
    .HaveDependencyOn("NetArchTest.SampleLibrary.Data")
    .GetResult()
    .IsSuccessful;

Nuestra charla sobre la testeabilidad resalta un problema con
cualquier métrica o medición: la posibilidad de que los
desarrolladores intenten manipular el sistema. Una vez que
aprenden cómo los arquitectos miden el cumplimiento, podrían
programar para la métrica en lugar de construir lo correcto. Por
ejemplo, un fallo común de testeabilidad ocurre cuando los
desarrolladores que toman atajos escriben pruebas unitarias, pero
sin ninguna aserción. "Tocar" el código pero no verificar que
funcione equivale a hacer trampa en la métrica de cobertura de

168código (code-coverage). Escribir código de gobernanza utilizando
herramientas como ArchUnit ayuda a los arquitectos a prevenir este
comportamiento al asegurar que cada prueba unitaria incluya al
menos una aserción. Por supuesto, los que se dedican a romper las
reglas siempre encontrarán la manera, pero las funciones de aptitud
como esta previenen descuidos accidentales.

Otro ejemplo de funciones de aptitud es el "Chaos Monkey" de
Netflix y el Simian Army que lo acompaña. Cuando Netflix decidió
trasladar sus operaciones a la nube de Amazon, los arquitectos
dejaron de tener el control sobre las operaciones, lo que les
preocupaba: ¿qué pasaría si aparecía un defecto operativo? Para
solucionar este problema, crearon la disciplina de la ingeniería del
caos. Chaos Monkey actúa esencialmente como una función de
aptitud de producción, simulando el caos general para ver qué tan
bien puede soportarlo el sistema. La latencia era un problema con
algunas instancias de AWS, por lo que Chaos Monkey simulaba una
latencia alta. (De hecho, esto fue un problema tal que terminaron
creando un Latency Monkey especializado). Esto los llevó a
desarrollar herramientas adicionales: por ejemplo, Chaos Kong, que
simula el fallo de un centro de datos completo de Amazon, ha
ayudado a Netflix a evitar tales interrupciones cuando ocurren en la
realidad.

En particular, los "monos" (funciones de aptitud) de Conformidad,
Seguridad y Conserje (Janitor) ejemplifican el enfoque de
gobernanza automatizada. El Conformity Monkey permite a los
arquitectos de Netflix definir reglas de gobernanza impuestas por el
mono en producción. Por ejemplo, si deciden que cada servicio debe
responder sin errores a todas las peticiones, integran esa
comprobación en el Conformity Monkey. El Security Monkey
comprueba cada servicio en busca de defectos de seguridad
conocidos, como puertos que no deberían estar activos y errores de
configuración.

169Finalmente, el Janitor Monkey busca instancias a las que ya ningún
otro servicio redirige tráfico. Netflix tiene una arquitectura evolutiva,
por lo que los desarrolladores migran rutinariamente a servicios más
nuevos, dejando los servicios antiguos funcionando sin
colaboradores. Debido a que ejecutar servicios en la nube cuesta
dinero, el Janitor Monkey busca servicios huérfanos y los elimina de
producción.

La ingeniería del caos ofrece una nueva perspectiva interesante
sobre la arquitectura: no es cuestión de si algo acabará
rompiéndose, sino de cuándo. Anticipar esas roturas y realizar
pruebas para prevenirlas hace que los sistemas sean mucho más
robustos. Un libro de algunos de los innovadores de Netflix, Casey
Rosenthal y Nora Jones, llamado Ingeniería del caos (O’Reilly, 2020),
destaca este enfoque.

El influyente libro de Atul Gawande, El manifiesto de la lista de
verificación (Metropolitan, 2009), describe cómo profesionales como
los pilotos de aerolíneas y los cirujanos utilizan listas de verificación.
(A veces, incluso se les exige legalmente que lo hagan). No es
porque estos profesionales no conozcan su trabajo o sean
olvidadizos. Más bien, cuando los profesionales realizan un trabajo
sumamente detallado una y otra vez, es fácil que se les escape
algún detalle; una lista de verificación sucinta constituye un
recordatorio eficaz.

Esta es la perspectiva correcta sobre las funciones de aptitud: no
son un mecanismo de gobernanza pesado, sino un mecanismo para
que los arquitectos expresen y verifiquen automáticamente
principios arquitectónicos importantes. Los desarrolladores saben
que no deben publicar código inseguro, pero eso compite con
decenas o cientos de otras prioridades. Las herramientas como el
Security Monkey, y las funciones de aptitud en general, permiten a
los arquitectos integrar comprobaciones de gobernanza importantes
en el sustrato de la arquitectura.


399Capítulo 15. Estilo de
arquitectura orientada a
eventos

El estilo de arquitectura orientada a eventos (EDA) es un estilo de
arquitectura distribuida y asíncrona muy popular, utilizado para
producir aplicaciones altamente escalables y de alto rendimiento.
También es particularmente adaptable y puedes usarlo tanto para
aplicaciones pequeñas como para las grandes y complejas. La
arquitectura orientada a eventos se compone de componentes de
procesamiento de eventos desacoplados que activan y responden a
eventos de forma asíncrona. Puedes usarla como un estilo de
arquitectura independiente o integrarla dentro de otros estilos de
arquitectura (como una arquitectura de microservicios orientada a
eventos).

Muchos desarrolladores y arquitectos de software consideran que la
EDA es más un patrón arquitectónico que un estilo arquitectónico.
Nosotros no estamos de acuerdo. Tus autores han desarrollado
sistemas completos que dependen únicamente de la EDA, razón por
la cual sostenemos que es primordialmente un estilo arquitectónico.
Si bien puedes usar la EDA en otros estilos arquitectónicos —como
microservicios y arquitectura basada en el espacio— para formar
arquitecturas híbridas, sigue siendo en su esencia una forma de
diseñar sistemas complejos.

La mayoría de las aplicaciones siguen lo que se llama un modelo
basado en peticiones, como se ilustra en la Figura 15-1. Cuando un
cliente solicita, por ejemplo, su historial de pedidos de los últimos
seis meses, esta petición es recibida inicialmente por un orquestador
de peticiones. El orquestador de peticiones suele ser una interfaz de

400usuario, pero también puede implementarse a través de una capa de
API, servicios de orquestación, centros de eventos, un bus de
eventos o un centro de integración. Su función es dirigir la petición a
varios procesadores de peticiones, de forma determinante y
síncrona. Estos procesan la petición recuperando y actualizando la
información del cliente en una base de datos. Recuperar la
información del historial de pedidos es una petición determinista y
basada en datos realizada al sistema dentro de un contexto
específico, no un evento que sucede al que el sistema debe
reaccionar, razón por la cual este es un modelo basado en
peticiones.

Un modelo basado en eventos, por otro lado, reacciona a un evento
particular tomando una acción. Por ejemplo, considera el envío de
una oferta en una subasta en línea para un artículo específico. El
postor que envía la oferta no está haciendo una petición al sistema,
sino que está iniciando un evento que ocurre después de que se
anuncia el precio de salida actual. El sistema debe responder a ese
evento comparando la oferta con otras recibidas al mismo tiempo y
determinando quién es el postor con la oferta más alta en ese
momento.

401Este  diagrama  ilustra  un  modelo  basado  en  solicitudes  en  el  que  una  solicitud

inicial  llega  a  un  orquestador  de  solicitudes,  el  cual  se  encarga  de  gestionar  el

estado  de  la  solicitud.  Este  orquestador  interactúa  con  varios  procesadores  de

solicitudes que contienen distintos componentes y mantienen también el estado de

la solicitud de forma interna. Finalmente, todos estos procesadores se comunican

bidireccionalmente  con  una  base  de  datos  central  para  realizar  las  consultas  o

actualizaciones  necesarias  y  completar  el  flujo  del  proceso.  (Accesibilidad  de  la

imagen)

Topología

Figura 15-1. Modelo basado en peticiones

La arquitectura orientada a eventos aprovecha la comunicación
asíncrona de lanzar y olvidar (fire-and-forget), donde los servicios
activan eventos y otros servicios responden a esos eventos. Los
cuatro componentes arquitectónicos principales de su topología son
un evento de inicio, un agente de eventos (event broker), un
procesador de eventos (generalmente llamado solo servicio) y un
evento derivado.

402El evento de inicio es el evento que arranca todo el flujo del evento.
Este podría ser un evento simple, como realizar una oferta en una
subasta en línea, o eventos más complejos, como realizar
actualizaciones en un sistema de beneficios de salud cuando un
empleado se casa. El evento de inicio se envía a un canal de eventos
en el agente de eventos para su procesamiento. Un único
procesador de eventos acepta el evento de inicio del agente de
eventos y comienza a procesar dicho evento.

El procesador de eventos que aceptó el evento de inicio realiza una
tarea específica asociada al procesamiento de ese evento (como
realizar una oferta por un artículo de subasta) y luego anuncia de
forma asíncrona lo que hizo al resto del sistema activando lo que se
llama un evento derivado hacia un agente de eventos. Otros
procesadores de eventos responden al evento derivado, realizan un
procesamiento específico basado en él y luego anuncian lo que
hicieron a través de nuevos eventos derivados. Este proceso
continúa hasta que todos los procesadores de eventos están
inactivos y todos los eventos derivados han sido procesados. La
Figura 15-2 ilustra este flujo de procesamiento de eventos.

403Este diagrama ilustra la topología básica de una arquitectura orientada a eventos,

comenzando  con  un  evento  inicial  que  se  transmite  a  través  de  un  canal  de

eventos  hacia  un  procesador  de  eventos  compuesto  por  distintos  componentes.

Tras  procesar  la  información,  este  genera  un  evento  derivado  que  viaja  por  otro

canal  de  eventos  para  ser  distribuido  a  múltiples  procesadores  de  eventos

adicionales.  El  flujo  se  extiende  cuando  uno  de  estos  últimos  emite  un  nuevo

evento  derivado,  el  cual  atraviesa  un  tercer  canal  de  eventos  hasta  alcanzar  a

otros  procesadores  de  eventos  finales,  demostrando  así  cómo  las  acciones  se

encadenan y se propagan de manera asíncrona por todo el sistema. (Accesibilidad

de la imagen)

Figura 15-2. Topología básica de una arquitectura orientada a eventos

El componente del agente de eventos suele estar federado (lo que
significa que tiene múltiples instancias agrupadas basadas en
dominios). Cada agente federado contiene todos los canales de
eventos (como colas y temas) utilizados dentro del flujo de eventos
(todo el flujo de trabajo para procesar el evento) para ese dominio
en particular. Debido a la naturaleza de difusión desacoplada,
asíncrona y de "lanzar y olvidar" de este estilo arquitectónico, la

404topología del agente utiliza temas (topics), intercambios de temas
(en el caso del Protocolo Avanzado de Colas de Mensajes (AMQP)) o
flujos (streams) con un modelo de mensajería de publicación y
suscripción.

Para ilustrar cómo funciona el procesamiento EDA en general,
considera el flujo de trabajo de un sistema típico de entrada de
pedidos minoristas, como se ilustra en la Figura 15-3, donde los
clientes pueden realizar pedidos de artículos (por ejemplo, un libro
como este). En este ejemplo, el procesador de eventos Order
Placement (Colocación de Pedidos) recibe el evento de inicio
(place order (realizar pedido)), inserta el pedido en una tabla de
base de datos y devuelve un ID de pedido al cliente. Luego anuncia
al resto del sistema que creó un pedido a través de un evento
derivado order placed (pedido realizado). Observa que tres
procesadores de eventos están interesados en ese evento derivado:
el procesador de eventos Notification (Notificación), el
procesador de eventos Payment (Pago) y el procesador de eventos
Inventory (Inventario), todos los cuales realizan sus tareas en
paralelo.

405Este  diagrama  ilustra  la  topología  de  una  arquitectura  dirigida  por  eventos  para

realizar un pedido de un libro. Todo comienza cuando el servicio de realización de

pedidos  genera  el  evento  de  pedido  realizado,  el  cual  activa  simultáneamente  al

servicio  de  pagos,  al  servicio  de  inventario  y  al  servicio  de  notificaciones.  El

servicio  de  inventario  genera  una  actualización  del  inventario  que  comunica  al

servicio  de  almacén,  el  cual  puede  notificar  cuando  las  existencias  han  sido

repuestas. Por su parte, el servicio de pagos puede dar lugar a un pago aplicado o

un  pago  denegado;  si  el  pago  es  denegado,  se  informa  al  servicio  de

notificaciones,  pero  si  es  aceptado,  se  activa  el  servicio  de  cumplimiento  de

pedidos. Una vez que este último marca el pedido como cumplido, el servicio de

envíos  procede  a  despacharlo,  generando  el  evento  de  pedido  enviado,  mientras

que el servicio de notificaciones se encarga de confirmar que el correo electrónico

406ha  sido  enviado  al  cliente  en  diversos  puntos  del  proceso.  (Accesibilidad  de  la

imagen)

Figura 15-3. Ejemplo de la topología de la arquitectura orientada a eventos

El procesador de eventos Notification (Notificación) recibe el
evento derivado order placed (pedido realizado) y envía un
correo electrónico al cliente con los detalles del pedido. Debido a
que el procesador de eventos Notification ha realizado una acción,
genera entonces un evento derivado email sent (correo enviado).
Sin embargo, observa en la Figura 15-3 que ningún otro procesador
de eventos está escuchando ese evento derivado. Esto es típico
dentro de EDA e ilustra la extensibilidad arquitectónica de este
estilo: la capacidad de que futuros procesadores de eventos
respondan al evento derivado sin ningún cambio en el sistema
existente (ver “Activación de eventos extensibles”).
El procesador de eventos Inventory (Inventario) también escucha
el evento derivado order placed (pedido realizado) y ajusta el
inventario correspondiente para ese libro. Luego anuncia esta acción
activando un evento derivado inventory updated (inventario
actualizado), que a su vez activa una respuesta del procesador de
eventos Warehouse (Almacén). Este procesador responde y gestiona
el inventario correspondiente entre almacenes, reabasteciendo
artículos si los suministros bajan demasiado. Cuando se repone el
stock, el procesador de eventos Warehouse activa un evento derivado
stock replenished (stock repuesto), al cual el procesador de
eventos Inventory responde ajustando el inventario actual.
En este caso, el procesador de eventos Inventory (Inventario) no
activaría un evento inventory adjusted (inventario ajustado)
correspondiente. Si lo hiciera, eso llevaría a lo que se llama un
evento venenoso (poison event): un evento que sigue en bucle una
y otra vez para siempre.

407ADVERTENCIA

Un evento venenoso ocurre cuando un evento derivado se activa y se
responde continuamente en un bucle infinito entre servicios. Estos
pueden ocurrir con frecuencia cuando se utiliza una arquitectura
orientada a eventos, así que ten cuidado para evitarlos.

El procesador de eventos Payment (Pago) también responde al
evento derivado order placed (pedido realizado). Responde
cargando la tarjeta de crédito del cliente. La Figura 15-3 muestra
que se generará uno de dos posibles eventos derivados como
resultado de la acción del procesador de eventos Payment: uno para
notificar al resto del sistema que se aplicó el pago (payment applied
(pago aplicado)), y otro para notificar al sistema que el pago fue
denegado (payment denied (pago denegado)). El procesador de
eventos Notification (Notificación) está interesado en el evento
derivado payment denied, porque si esto sucede, necesita enviar un
correo electrónico al cliente informándole que debe actualizar la
información de su tarjeta de crédito o elegir un método de pago
diferente.
El procesador de eventos Order Fulfillment (Cumplimiento de
Pedidos) escucha el evento derivado payment applied (pago
aplicado) y realiza varias funciones automatizadas dentro del
proceso de recolección y embalaje, como indicarle al trabajador
dónde encontrar el artículo y qué tamaño de caja se necesita para el
pedido. Una vez que eso se completa, activa un evento derivado
order fulfilled (pedido cumplido) indicando al resto del sistema
que ha cumplido con el pedido. Tanto el procesador de eventos
Notification (Notificación) como el de Shipping (Envío)
escuchan este evento derivado. Simultáneamente, el procesador de
eventos Notification notifica al cliente que el pedido se ha
cumplido y está listo para el envío, y el procesador de eventos
Shipping selecciona un método de envío, envía el pedido y emite un

408evento derivado order shipped (pedido enviado). El procesador de
eventos Notification también escucha el evento derivado order
shipped y notifica al cliente que el pedido está en camino.

Todos los procesadores de eventos están altamente desacoplados y
son independientes entre sí. Una forma de entender este flujo de
trabajo de procesamiento asíncrono es pensar en él como una
carrera de relevos. En una carrera de relevos, los corredores
sostienen una batuta (un palo de madera) y corren una cierta
distancia (digamos, 1.5 kilómetros), luego entregan la batuta al
siguiente corredor, quien hace lo mismo, siguiendo la cadena hasta
que el último corredor cruza la línea de meta. Una vez que un
corredor entrega la batuta, ese corredor ha terminado con la carrera
y puede pasar a otras cosas. Esto también es cierto para los
procesadores de eventos: una vez que un procesador de eventos
entrega un evento, ya no está involucrado en el procesamiento de
ese evento específico y queda disponible para reaccionar a otros
eventos de inicio o derivados. Además, cada procesador de eventos
puede escalar de forma independiente para manejar condiciones de
carga variables o acumulaciones.

Especificaciones del estilo

Las siguientes secciones describen la EDA con más detalle,
incluyendo algunas consideraciones, patrones e híbridos de este
complejo estilo arquitectónico.

Eventos frente a mensajes

La arquitectura orientada a eventos aprovecha los eventos para
pasar y procesar información. Pero, ¿es un evento realmente tan
diferente de un mensaje? Resulta que sí, realmente lo es.

Un evento difunde a otros procesadores de eventos que algo ya ha
sucedido: "Acabo de realizar un pedido". Un mensaje, sin embargo,

409es más bien un comando o una consulta, como "aplica el pago para
este pedido" o "dame las opciones de envío para este pedido". Esta
no es una diferencia sutil. Cuando hablamos de procesamiento de
eventos, nos referimos a reaccionar a algo que ya ha sucedido,
mientras que un mensaje describe algo que debe hacerse. En
nuestro ejemplo, está claro que "Acabo de realizar un pedido" es un
evento porque no describe qué procesamiento debe ocurrir, como lo
haría un mensaje. Esto ilustra la naturaleza desacoplada de la EDA.

La segunda diferencia principal entre un evento y un mensaje es que
un evento típicamente no requiere una respuesta del receptor,
mientras que un mensaje usualmente sí. Esto reduce la
comunicación de ida y vuelta entre los procesadores de eventos,
desacoplándolos aún más entre sí.

Otra diferencia importante entre eventos y mensajes es que un
evento suele difundirse a múltiples procesadores de eventos,
mientras que un mensaje casi siempre se dirige a un solo procesador
de eventos. En nuestro sencillo ejemplo de procesamiento de
pedidos, varios procesadores de eventos están interesados y
responden al evento order created (pedido creado), mientras que
solo un procesador de eventos responde al mensaje apply payment
(aplicar pago). Los eventos suelen utilizar una forma de
comunicación de publicación y suscripción (uno a muchos), mientras
que los mensajes suelen utilizar una forma de comunicación de
punto a punto (uno a uno).

Una diferencia final entre eventos y mensajes es el artefacto físico
que representa el canal de comunicación. Los eventos utilizan un
tema (topic), flujo (stream) o servicio de notificación para que
múltiples procesadores de eventos puedan suscribirse al canal y
escuchar el evento. La mensajería suele utilizar una cola o servicio
de mensajería para garantizar que solo un tipo de procesador de
eventos reciba ese mensaje.

410La arquitectura orientada a eventos utiliza principalmente eventos
(de ahí su nombre), pero puede utilizar mensajes en ocasiones,
como al solicitar datos de otro procesador de eventos (ver
“Topologías de datos” y “Procesamiento de petición-respuesta”). Más
adelante en este capítulo, te mostraremos la arquitectura orientada
a eventos mediada (ver “Arquitectura orientada a eventos
mediada”), que utiliza mensajes para controlar el orden de
procesamiento de los eventos.

¿Puedes identificar cuáles de las siguientes opciones son eventos y
cuáles son mensajes?

"Vuelo 6557 de Adventurous Air, gira a la izquierda, rumbo
230 grados".

"En otras noticias, un frente frío se ha desplazado hacia la
zona".

"Muy bien, clase, vayan a la página 145 de sus libros de
trabajo".

"¡Hola a todos! Siento llegar tarde a la reunión".

Veámoslos uno por uno:

"Vuelo 6557 de Adventurous Air, gira a la izquierda, rumbo 230
grados".

Esto es un mensaje porque es una orden (algo que debe
hacerse) y porque está dirigido a un solo destinatario, el
piloto, aunque varios otros pilotos puedan escuchar el
mensaje.

"En otras noticias, un frente frío se ha desplazado hacia la zona".

Esto es un evento: se está difundiendo a múltiples personas,
describe algo que ya ha sucedido y el locutor de noticias no
espera una respuesta. (Sin embargo, hay algunos mensajes
que tampoco requieren respuesta).

411"Muy bien, clase, vayan a la página 145 de sus libros de trabajo".

Este es un poco capcioso. Resulta que es un mensaje, aunque
se esté difundiendo a múltiples estudiantes. Es una orden
para hacer algo, no algo que ya ha sucedido (lo que lo
convertiría en un evento). Esto ilustra un punto importante
sobre la diferencia entre un evento y un mensaje: difundir
una orden (como ir a la página 145 en los libros de trabajo) a
través de un canal de publicación y suscripción no la
convierte en un evento.

"¡Hola a todos! Siento llegar tarde a la reunión".

Esto es un evento, porque el hecho de que esta persona
llegue tarde a la reunión ya ha sucedido. También se está
difundiendo a múltiples personas y no se espera respuesta.

Eventos derivados

Los eventos derivados son una parte crítica y necesaria de la EDA.
Son creados y activados por procesadores de eventos después de
recibir el evento inicial. Un procesador de eventos puede activar más
de un evento derivado, basándose en su procesamiento.

Considera los eventos derivados activados cuando el procesador de
eventos Payment (Pago) carga la tarjeta de crédito de un cliente por
una compra en la Figura 15-3. Como se ilustra en la Figura 15-4,
cargar una tarjeta de crédito implica verificar un posible fraude
(procesado por el procesador de eventos Fraud Detection
(Detección de Fraude)) y verificar el saldo de la tarjeta de crédito
(procesado por el procesador de eventos Credit Limit (Límite de
Crédito)). La EDA puede aprovechar un único evento (creditcard
charged (tarjeta de crédito cargada)) para realizar ambas
actividades al mismo tiempo.

412Este diagrama de flujo ilustra una arquitectura dirigida por eventos que comienza

con  el  servicio  de  realización  de  pedidos,  el  cual  dispara  el  evento  de  pedido

realizado. Este evento es recibido por el servicio de pagos, que a su vez genera la

notificación  de  pago  aplicado.  A  partir  de  aquí,  el  flujo  se  divide  hacia  dos

procesos  paralelos:  el  servicio  de  detección  de  fraudes  y  el  servicio  de  límite  de

crédito.  El  componente  de  detección  de  fraudes  puede  emitir  los  eventos  de

fraude  detectado  o  sin  fraude  detectado.  Por  su  parte,  el  servicio  de  límite  de

crédito  evalúa  la  transacción  y  puede  generar  tres  respuestas  distintas  según  el

estado  de  la  cuenta:  límite  correcto,  advertencia  de  límite  o  límite  excedido.

(Accesibilidad de la imagen)

Figura 15-4. Los eventos derivados se generan en respuesta al evento inicial

Nota cuántos eventos derivados genera esta única acción. En el
procesador de eventos Fraud Detection (Detección de Fraude), se
activan dos posibles eventos derivados: uno si el procesador detecta
fraude y otro si no se detecta fraude. Ambos eventos derivados son
necesarios, porque diferentes procesadores de eventos podrían
tomar acciones adicionales dependiendo del resultado de la
detección de fraude.

Ahora observa los eventos derivados del procesador de eventos
Credit Limit (Límite de Crédito). Primero, un evento derivado
limit okay (límite correcto) indica al resto del sistema que no
hay riesgo para esta compra y que el cliente tiene suficiente crédito

413disponible. De hecho, este evento en particular también podría
almacenar en su carga útil (payload) la cantidad de crédito que le
queda al cliente, lo cual podría ser de interés para los procesadores
de eventos posteriores. Segundo, el evento derivado limit warning
(advertencia de límite), que advierte que el saldo de la tarjeta
está cerca del límite de crédito, podría interesar a otros
procesadores de eventos posteriores; por ejemplo, el procesador de
eventos Notification (Notificación), que podría notificar al
cliente que está cerca de su límite de crédito. Por último, el fatal
evento derivado limit exceeded (límite excedido) es de interés
para varios procesadores de eventos, incluyendo Notification,
Decline Purchase (Rechazar Compra) y quizás un procesador de
eventos de marketing Extend Credit Limit (Ampliar Límite de
Crédito) que amplíe automáticamente el límite de crédito del cliente
para permitir la compra.

Esto ilustra que se puede activar más de un evento derivado desde
un procesador de eventos. Sin embargo, ten cuidado de no caer en
el antipatrón Enjambre de Mosquitos (Swarm of Gnats), donde una
unidad de procesamiento envía demasiados eventos de grano fino
(ver “El antipatrón Enjambre de Mosquitos”).

Activación de eventos extensibles

En la EDA, suele ser una buena práctica que cada procesador de
eventos comunique lo que ha hecho al resto del sistema,
independientemente de si a algún otro procesador de eventos le
importa o no cuál fue esa acción.

Cuando ningún procesador de eventos se interesa o responde al
evento, lo llamamos un evento derivado extensible porque, aun así,
proporciona soporte para la extensibilidad arquitectónica al ofrecer
un "hook" (gancho) incorporado en caso de que el procesamiento de
ese evento requiera funcionalidad adicional. Por ejemplo, supón que,
como parte de un proceso de eventos complejo (como se ilustra en

414la Figura 15-5), el procesador de eventos Notification
(Notificación) genera un correo electrónico que envía a un cliente,
notificándole sobre una acción particular. Luego comunica que ha
enviado el correo al resto del sistema a través de un nuevo evento
derivado (email sent (correo enviado)). Dado que ningún otro
procesador de eventos está escuchando o respondiendo a ese
evento en este momento, el mensaje simplemente desaparece (o se
ignora, en el caso del flujo de eventos). Eso podría parecer un
desperdicio de recursos, pero no lo es. Supón que la empresa decide
analizar todos los correos electrónicos enviados a los clientes. El
equipo puede añadir un nuevo procesador de eventos Email
Analyzer (Analizador de Correos) al sistema general con un
esfuerzo mínimo y sin cambios en otros procesadores de eventos,
porque la información del correo ya está disponible a través del
evento derivado email sent.

415Esta  ilustración  describe  el  flujo  de  una  arquitectura  orientada  a  eventos  que

comienza  cuando  el  cliente  realiza  un  pedido,  activando  el  componente  de

realización del pedido. Una vez que se genera el evento de pedido realizado, este

se  distribuye  hacia  tres  procesadores  distintos:  el  de  pago,  el  de  gestión  de

inventario y el de notificación. El proceso de pago resulta en un pago aplicado y la

gestión de inventario en una actualización de inventario, tras lo cual se indica que

otros  procesadores  de  eventos  están  respondiendo  a  estos  eventos  específicos.

Por su parte, el procesador de notificación dispara el evento de correo electrónico

enviado, aclarando que, en este punto del sistema, nadie está respondiendo a este

evento final. (Accesibilidad de la imagen)

Figura 15-5. El evento Notification se envía, pero se ignora y no se utiliza

Capacidades asíncronas

El estilo arquitectónico orientado a eventos tiene una característica
única en la cual se basa principalmente en la comunicación
asíncrona tanto para el procesamiento de disparar y olvidar (no se
requiere respuesta) como para el procesamiento de
petición/respuesta (cuando se requiere una respuesta del
consumidor del evento, ver “Procesamiento de petición-respuesta”).
La comunicación asíncrona puede ser una técnica poderosa para
aumentar la capacidad de respuesta general de un sistema.

416En la Figura 15-6, un usuario está publicando una reseña de
producto en un sitio web. El servicio de comentarios, en este
ejemplo, tarda 3,000 milisegundos en validar y publicar ese
comentario. El comentario tiene que pasar por varios motores de
análisis: una verificación de palabras inaceptables, una verificación
para asegurarse de que el comentario no indique texto abusivo
(como "lento para razonar" o "incapaz de pensar con claridad") y,
finalmente, una verificación de contexto para asegurarse de que el
comentario sea sobre el producto (y no, por ejemplo, solo una
diatriba política).

La ruta superior en la Figura 15-6 publica el comentario usando una
llamada RESTful síncrona. Eso significa 50 ms de latencia de red
para que el servicio reciba la publicación, 3,000 ms para validar y
publicar el comentario, y 50 ms de latencia para decirle al usuario
que el comentario fue publicado. El tiempo total para publicar un
comentario, desde el punto de vista del usuario, es por lo tanto de
3,100 milisegundos. Ahora mira la ruta inferior, que utiliza
mensajería asíncrona. Aquí, el tiempo total de publicación del
usuario es de solo 25 ms, en lugar de 3,100 ms. Al sistema todavía
le toma 25 ms recibir el comentario y 3,000 ms publicarlo, para un
total de 3,025 ms, pero desde la perspectiva del usuario final, solo
transcurren 25 ms antes de que el sistema responda que ha
aceptado el comentario (aunque en realidad aún no se haya
publicado).

417Esta  ilustración  compara  los  modelos  de  comunicación  sincrónica  y  asincrónica

entre  un  productor  de  eventos  y  un  consumidor  de  eventos,  detallando  sus

componentes internos y tiempos de respuesta. En la parte superior, se observa un

flujo  sincrónico  mediante  una  transferencia  de  estado  representacional  donde  el

productor  entra  en  estado  de  espera;  tras  cincuenta  milisegundos  de  latencia,  el

consumidor  procesa  la  solicitud  durante  tres  mil  milisegundos  y  devuelve  la

respuesta  en  otros  cincuenta  milisegundos,  sumando  un  tiempo  total  de  tres  mil

cien  milisegundos  antes  de  que  el  productor  reciba  la  señal  para  seguir.  En

contraste,  la  parte  inferior  muestra  el  modelo  asincrónico,  donde  el  productor

envía  el  mensaje  a  través  de  un  canal  en  solo  veinticinco  milisegundos,

permitiendo  que  la  señal  de  espera  cambie  a  una  de  avance  casi  de  inmediato;

así,  aunque  el  consumidor  tarde  los  mismos  tres  mil  milisegundos  en  su

procesamiento

interno,  el  tiempo  percibido  por  el  productor  se  reduce

drásticamente,  optimizando  la  capacidad  de  respuesta  del  sistema.  (Accesibilidad

de la imagen)

Figura 15-6. Comunicación síncrona frente a asíncrona

La diferencia en el tiempo de respuesta entre 3,100 ms y 25 ms es
asombrosa. Sin embargo, hay una advertencia: en la ruta superior
síncrona, el usuario final obtiene una garantía de que su comentario
ha sido publicado. En cambio, en la ruta inferior asíncrona, solo se
confirma la recepción de la publicación, con la promesa futura de

418que eventualmente será publicada. ¿Qué pasaría si el comentario del
usuario incluye palabras obscenas y el sistema lo rechaza? No hay
forma de que se lo notifique al usuario final... ¿o sí la hay? Si el
usuario debe registrarse en el sitio web para publicar un comentario,
el sistema podría enviarle un mensaje indicando un problema con el
comentario y sugiriendo cómo corregirlo.

Este ejemplo ilustra la diferencia entre la capacidad de respuesta (el
tiempo que tarda en devolver la información al usuario) y el
rendimiento (el tiempo que tarda en insertar el comentario en la
base de datos). Cuando el usuario no necesita que se le devuelva
ninguna información (más que un acuse de recibo o un mensaje de
agradecimiento), ¿por qué hacerlo esperar? La capacidad de
respuesta consiste en notificar al usuario que la acción ha sido
aceptada y que será procesada momentáneamente, mientras que el
rendimiento consiste en hacer que el proceso de extremo a extremo
sea más rápido. En la ruta inferior asíncrona, el arquitecto no hizo
nada para optimizar la forma en que el servicio de comentarios
procesa el comentario (eso es abordar la capacidad de respuesta). Si
el arquitecto se tomara el tiempo para optimizar el servicio de
comentarios, quizás ejecutando todos los motores de análisis de
texto y gramática en paralelo, aprovechando el almacenamiento en
caché y otras técnicas similares pero manteniendo el uso de
comunicación síncrona, estaría en su lugar abordando el rendimiento
general.

Ese fue un ejemplo sencillo. ¿Qué tal uno más complicado? Esta vez,
veamos una operación bursátil en línea, donde un usuario está
comprando algunas acciones de forma asíncrona. ¿Qué pasa si no
hay forma de notificar al usuario de un error?

Si bien la comunicación asíncrona mejora significativamente la
capacidad de respuesta, el manejo de errores es un gran problema.
La dificultad de abordar las condiciones de error aumenta la
complejidad de este estilo de arquitectura. “Manejo de errores”
ilustra un patrón de arquitectura reactiva para abordar los desafíos

419del manejo de errores: el patrón de Evento de flujo de trabajo
(Workflow Event).

Además de su capacidad de respuesta, la comunicación asíncrona
también proporciona un buen nivel de desacoplamiento dinámico y
evita un antipatrón, el Entrelazamiento Cuántico Dinámico (Dynamic
Quantum Entanglement), que ocurre cuando dos cuantos
arquitectónicos se comunican mediante comunicación síncrona.
(Probablemente recuerdes del Capítulo 7 que un cuanto
arquitectónico es una parte del sistema que puede desplegarse
independientemente del resto del sistema y que está vinculada
mediante un acoplamiento dinámico síncrono, y que las
características arquitectónicas residen a nivel de cuanto). Debido a
que estos dos cuantos arquitectónicos ahora dependen el uno del
otro, se vuelven esencialmente entrelazados. La dependencia los
convierte en un único cuanto arquitectónico. La comunicación
asíncrona puede ayudar a desenredar los cuantos arquitectónicos
porque elimina esa dependencia dinámica.

Para ilustrar este punto tan importante, considera los dos sistemas
en la Figura 15-7. En este ejemplo, el sistema Portfolio Management
(Gestión de Carteras) crea una orden bursátil para comprar
algunas acciones. Envía de forma síncrona esta orden de
negociación al sistema Trade Order (Orden de Negociación), el
cual realizará comprobaciones de cumplimiento y creará la orden
bursátil. Debido a que la comunicación entre estos dos sistemas es
síncrona, el sistema Portfolio Management debe necesariamente
bloquearse y esperar un número de confirmación de la negociación
por parte del sistema Trade Order. Estos dos sistemas se han
entrelazado y ahora forman un único cuanto arquitectónico.

420Esta  imagen  presenta  un  diagrama  técnico  que  ilustra  la  relación  entre  dos

componentes de software dentro de un mismo límite sistémico, representado por

un  borde  punteado.  A  la  izquierda,  se  observa  un  bloque  correspondiente  al

"Sistema  de  gestión  de  portafolio",  el  cual  se  conecta  mediante  una  flecha  hacia

un bloque a la derecha denominado "Sistema de órdenes de negociación". Sobre

la  flecha  que  indica  el  flujo  de  comunicación,  el  texto  señala  que  una  "llamada

síncrona da como resultado un único cuanto arquitectónico", lo que explica cómo

la  dependencia  directa  entre  ambos  servicios  los  integra  en  una  sola  unidad

operativa desde el punto de vista de la arquitectura. (Accesibilidad de la imagen)

Figura 15-7. Estos sistemas forman un único cuanto arquitectónico debido al
acoplamiento dinámico síncrono

La importancia de este entrelazamiento es que las características
arquitectónicas ahora residen entre estos dos sistemas. Si el sistema
Trade Order deja de estar disponible o no responde, el sistema
Portfolio Management no puede enviar la orden bursátil. Esto
también degrada la capacidad de respuesta: si el sistema Trade
Order es lento, el sistema Portfolio Management también lo será. La
escalabilidad también se ve afectada porque si el sistema Portfolio
Management necesita escalar, también debe hacerlo el sistema Trade
Order. Si no lo hace o no puede, entonces el sistema Portfolio
Management no podrá escalar según lo necesite.

Un arquitecto puede desenredar estos cuantos arquitectónicos
reemplazando la llamada síncrona por una llamada asíncrona entre
los dos sistemas, como se ilustra en la Figura 15-8.

421Este diagrama ilustra cómo una llamada asíncrona entre el sistema de gestión de

portafolios  y  el  sistema  de  órdenes  de  negociación  da  como  resultado  cuantos

arquitectónicos  separados.  Se  observa  una  flecha  punteada  que  conecta  ambos

bloques  para  representar  este  tipo  de  comunicación,  mientras  que  los  recuadros

punteados  individuales  que  rodean  a  cada  sistema  destacan  visualmente  su

independencia operativa y estructural dentro de la arquitectura.  (Accesibilidad de

la imagen)

Figura 15-8. Estos sistemas forman cuantos arquitectónicos separados debido a su
acoplamiento dinámico asíncrono

Al utilizar la comunicación asíncrona, el sistema Portfolio
Management (Gestión de Carteras) puede enviar la orden bursátil a
través de una cola o algún otro medio asíncrono, de modo que no
tenga que esperar a que el sistema Trade Order (Orden de
Negociación) cree la orden. Una vez que el sistema Trade Order
realiza sus comprobaciones de cumplimiento y crea la orden bursátil,
puede enviar el número de confirmación al sistema Portfolio
Management a través de un canal asíncrono separado. Eliminar esta
dependencia del acoplamiento dinámico de los dos sistemas les
permite formar dos cuantos arquitectónicos separados. Si el sistema
Trade Order no está disponible o no responde, el sistema Portfolio
Management aún puede emitir órdenes bursátiles, sabiendo que en
algún momento se crearán y se devolverán los números de
confirmación.

Capacidades de difusión
Otra de las características únicas de la EDA es su capacidad para
difundir (broadcast) eventos sin saber qué otras unidades de

422procesamiento (si las hay) están recibiendo esos eventos o qué
procesamiento realizarán en respuesta. Como muestra la Figura 15-
9, esto desacopla dinámicamente los procesadores de eventos entre
sí.

423Este  diagrama  ilustra  la  capacidad  de  difusión  de  eventos  dentro  de  una

arquitectura  dirigida  por  eventos,  donde  un  procesador  de  eventos  situado  a  la

izquierda,  compuesto  por  dos  componentes  internos,  emite  un  evento  que  se

transmite  a  través  de  un  canal  hacia  otros  tres  procesadores  de  eventos  a  la

derecha.  Cada  uno  de  estos  procesadores  receptores  cuenta  también  con  sus

propios  componentes

internos  para  gestionar

la

información  de  manera

independiente.  El  esquema  resalta  el  desacoplamiento  semántico  del  sistema,  ya

que el procesador inicial simplemente difunde el evento sin necesidad de conocer

qué  otras  unidades  lo  recibirán  o  qué  acciones  realizarán  en  respuesta.

(Accesibilidad de la imagen)

Figura 15-9. Difusión de eventos a otros procesadores de eventos

Las capacidades de difusión son una parte esencial de muchos
patrones, incluyendo la consistencia eventual y el procesamiento de
eventos complejos (CEP). Por ejemplo, los precios de los

424instrumentos negociados en el mercado de valores cambian con
frecuencia. Cada vez que se publica un nuevo precio de cotización
(el precio actual de una acción en particular), muchos procesadores
de eventos podrían responder al nuevo precio (como análisis de
operaciones, o la compra o venta de acciones). Sin embargo, el
procesador de eventos que publica el último precio simplemente lo
difunde, sin conocimiento de cómo se utilizará esa información. Esto
se conoce como desacoplamiento semántico en el sentido de que un
procesador de eventos no tiene conocimiento (ni dependencia) de
las acciones de otros procesadores de eventos.

Carga útil del evento

La información contenida en un evento se conoce como su carga útil
(payload). Las cargas útiles pueden variar significativamente: la
carga útil de un evento podría ser un simple par clave-valor, o toda
la información necesaria para el procesamiento posterior. Los dos
tipos básicos son las cargas útiles de eventos basadas en datos y
basadas en claves. Los arquitectos deben realizar un análisis
cuidadoso de las compensaciones (trade-offs) para determinar cuál
de estas opciones se adapta a cada tipo de evento activado en el
sistema. En esta sección, describimos estos dos tipos de carga útil y
sus correspondientes ventajas y desventajas.

Cargas útiles de eventos basadas en datos

Una carga útil de evento basada en datos es una carga útil de
evento que envía toda la información necesaria para el
procesamiento. En el ejemplo ilustrado en la Figura 15-10, un cliente
realiza un pedido. Primero, el procesador de eventos Order
Placement (Colocación de Pedidos) inserta el pedido completo en
la base de datos (el sistema de registro). Luego difunde un evento
llamado order_placed (pedido_realizado), que contiene todos los
detalles del pedido (en este caso, 45 atributos, que suman un total
de 500 KB de memoria). El procesador de eventos Payment (Pago)

425responde a este evento extrayendo información de la carga útil del
evento (específicamente el ID del pedido, la información del cliente y
el costo total del pedido) y usándola para aplicar el pago.
Simultáneamente, el procesador de eventos Inventory Management
(Gestión de Inventario) utiliza el ID del artículo y la cantidad de
artículos de la carga útil del evento para ajustar el inventario actual
del artículo comprado.

Este  diagrama  técnico  ilustra  el  funcionamiento  de  las  cargas  útiles  de  eventos

basadas en datos dentro de una arquitectura. El proceso comienza en el servicio

de realización de pedidos, el cual, por un lado, inserta el pedido directamente en

una base de datos y, por otro, envía un mensaje a través de un canal de eventos.

Se especifica que el resto de los datos se encuentran en la carga útil del evento, lo

que  permite  que  la  información  fluya  hacia  el  servicio  de  pago  y  el  servicio  de

inventario.  La  característica

fundamental  de  este  modelo  es  que  estos

procesadores de eventos no necesitan consultar la base de datos para procesar el

evento,  ya  que  disponen  de  toda  la  información  necesaria  dentro  del  propio

mensaje. (Accesibilidad de la imagen)

Figura 15-10. Las cargas útiles de eventos basadas en datos contienen todos los
datos necesarios para el procesamiento

Los procesadores de eventos Payment (Pago) e Inventory
Management (Gestión de Inventario) no tuvieron que consultar la

426base de datos para obtener la información del pedido, porque los
datos ya estaban contenidos en la carga útil del evento. Esta es una
de las mayores ventajas de usar cargas útiles de eventos basadas en
datos. Cuanto menos consulte un procesador de eventos la base de
datos, mejores serán su rendimiento, capacidad de respuesta y
escalabilidad. Además, dada la naturaleza de desacoplamiento
altamente dinámico de la EDA, el procesador de eventos Order
Placement (Colocación de Pedidos) podría no saber qué otros
procesadores de eventos están respondiendo al evento o qué datos
podrían necesitar para el procesamiento. Enviar toda la información
en la carga útil del evento garantiza que cada procesador de eventos
que responda tendrá la información necesaria para realizar su
procesamiento. Los procesadores de eventos podrían incluso no
tener acceso a la base de datos que contiene la información del
pedido, particularmente en topologías de datos con contextos
delimitados estrictos, basados en el dominio o con una base de
datos por servicio (ver “Topologías de datos”).

Si bien estas ventajas demuestran formas de crear sistemas más
responsivos, escalables y flexibles, las cargas útiles basadas en datos
tienen varias desventajas. La primera es que es más difícil mantener
la consistencia e integridad de los datos cuando tienes múltiples
sistemas de registro. Debido a que toda la información del pedido
está contenida en la base de datos y en los eventos que se activan
en el sistema, la información del pedido puede desincronizarse
fácilmente, especialmente si el pedido se actualiza durante el
procesamiento.

Por ejemplo, supón que un cliente realiza un pedido de cien
artículos, pero solo pretendía pedir uno, y se da cuenta de su error
inmediatamente después de enviar el pedido. O tal vez el cliente se
da cuenta justo después de pedir que ha utilizado la dirección de
envío incorrecta (esto les ha sucedido a tus autores muchas veces).
En cualquiera de estas situaciones, el cliente actualiza
inmediatamente el pedido con la información correcta. La base de

427datos, que es el único sistema de registro, contiene los valores
corregidos, pero es posible que algunos de los eventos que
contienen los valores antiguos no se procesen de inmediato. Esto
significa que cualquiera de los valores antiguos e incorrectos que
aún se estén procesando se utilizará en lugar de los nuevos y
correctos. Para complicar aún más este escenario, es muy difícil en
la EDA controlar el cronometraje de los eventos, por lo que es
posible que los valores más nuevos se procesen antes que los
valores más antiguos. Esto significa que si otros procesadores de
eventos utilizan los valores antiguos e incorrectos, estos podrían
sobreponerse a los valores correctos y más nuevos.

Una segunda desventaja importante de la carga útil del evento
basada en datos se refiere a la gestión de contratos y al versionado.
Sabemos que un pedido en este sistema tiene 45 atributos. Debido a
que toda esa información está contenida en la carga útil del evento,
el evento necesita algún tipo de contrato: una forma de estructurar
los datos que se envían. El arquitecto se enfrenta ahora a un sinfín
de decisiones: ¿debería el tipo de carga útil ser un objeto JSON? ¿Un
objeto XML? ¿Debería el contrato ser estricto o flexible? (Un contrato
estricto es aquel que utiliza algún tipo de esquema o definición de
objeto, como un esquema JSON, una especificación GraphQL o una
definición de clase; mientras que un contrato flexible podría utilizar
simples pares nombre-valor de JSON). Cada una de estas decisiones
conlleva muchas compensaciones (trade-offs), y cada una forma un
fuerte acoplamiento estático entre los procesadores de eventos.

Y luego está el versionado. Para contratos estrictos, un arquitecto o
desarrollador podría usar un tipo MIME del proveedor en los
encabezados del evento para especificar el número de versión. Esto
ayuda a que el sistema sea más ágil y proporciona compatibilidad
hacia atrás (para evitar romper otros procesadores de eventos). Sin
embargo, todos los procesadores de eventos deben aprovechar la
misma lógica de versionado, lo que requiere una gobernanza sólida.
Si un procesador de eventos ignora una versión del contrato al

428responder a la carga útil de un contrato estricto, es probable que
cambiar ese esquema provoque que dicho procesador de eventos
falle. Además, es muy difícil implementar estrategias de
comunicación de versiones y de depreciación en una arquitectura
asíncrona y altamente desacoplada como la EDA. Todo esto hace
que las cargas útiles de eventos basadas en datos sean algo frágiles.

Las cargas útiles de eventos basadas en datos también pueden sufrir
de acoplamiento de marca (stamp coupling): una forma de
acoplamiento estático donde varios módulos (en este caso,
procesadores de eventos) comparten una estructura de datos
común, pero solo usan partes de ella (y en muchos casos, partes
diferentes). Cuando ocurre esta situación, cambiar la estructura de
datos común puede requerir cambiar otros procesadores de eventos,
incluso aquellos a los que no les importan los datos.

La Figura 15-11 ilustra cómo funciona el acoplamiento de marca y su
impacto negativo en la arquitectura. En este ejemplo, el procesador
de eventos Order Placement (Colocación de Pedidos) envía un
evento order_placed (pedido_realizado) que consta de 45
atributos, contiene toda la información sobre el pedido y tiene un
tamaño de 500 KB. El procesador de eventos Inventory
(Inventario) responde al evento order_created (pedido_creado),
pero solo requiere dos atributos, el item_id y la quantity, que
suman solo 30 bytes. En este ejemplo, cambiar la carga útil, por
ejemplo eliminando un atributo de línea de dirección, afectaría al
procesador de eventos Inventory a pesar de que no le importa ese
campo.

429Esta ilustración muestra un diagrama técnico sobre el acoplamiento de datos entre

dos  servicios.  A  la  izquierda,  el  Servicio  de  colocación  de  pedidos  envía  un

mensaje  con  múltiples  campos  como  identificación  del  pedido,  del  cliente  y  del

artículo, cantidad, descripción, monto total, nombre del cliente, dirección y estado.

A  la  derecha,  el  Servicio  de  inventario  recibe  esta  información,  pero  una  nota

indica que «estos son los únicos atributos utilizados», señalando específicamente

al código del artículo y la cantidad. Sin embargo, un mensaje en la parte inferior

advierte que «agregar un campo requiere un cambio en el inventario, aunque este

no  lo  utilice»,  lo  que  resalta  el  problema  de  dependencia  innecesaria  entre  los

componentes  cuando  comparten  una  estructura  de  datos  demasiado  extensa.

(Accesibilidad de la imagen)

Figura 15-11. Un ejemplo de acoplamiento de marca, donde otro servicio solo
necesita parte de los datos enviados

En este ejemplo, usar el versionado de contratos con contratos
estrictos ayuda a mitigar el riesgo de que el procesador de eventos
Inventory (Inventario) falle, pero en algún momento —cuando la
versión del contrato quede obsoleta o se produzca un cambio de

430contrato que rompa la compatibilidad— un desarrollador tendrá que
volver a probarlo y desplegarlo.

Un problema del acoplamiento de marca que suele pasarse por alto
es la utilización del ancho de banda. La tercera falacia de la
computación distribuida es que "el ancho de banda es infinito". No lo
es, por supuesto. De hecho, en la mayoría de los entornos basados
en la nube, el ancho de banda es lo que más cuesta. Volviendo a
nuestro ejemplo en la Figura 15-11, con una carga útil basada en
datos, si los clientes realizan 500 pedidos por segundo, enviar un
solo evento de 500 KB al procesador de eventos Inventory
(Inventario) utilizará 250,000 KB por segundo de ancho de banda.
Sin embargo, si el sistema envía solo los 30 bytes de datos
realmente necesarios, el evento solo utilizará 15 KB por segundo de
ancho de banda. Esta es una diferencia asombrosa, que vale la pena
investigar cuando se utilizan cargas útiles de eventos basadas en
datos.

Una razón por la que los arquitectos a veces limitan el acoplamiento
de marca es para aprovechar los contratos impulsados por el
consumidor (consumer-driven contracts), donde cada consumidor de
un mensaje tiene su propio contrato que contiene solo los datos que
necesita para el procesamiento. Sin embargo, debido a las
capacidades de difusión de la EDA y a que el sistema no siempre
puede saber qué procesadores de eventos responderán a un evento,
es difícil aprovechar los contratos impulsados por el consumidor con
eventos en una arquitectura orientada a eventos. Por esta razón (y
para abordar las otras desventajas de las cargas útiles de eventos
basadas en datos), muchos arquitectos recurren a las cargas útiles
de eventos basadas en claves.

Carga útil de evento basada en claves

Una carga útil de evento basada en claves es una carga útil de
evento que contiene solo una clave que identifica el contexto del
evento (como un ID de pedido o un ID de cliente). Con las cargas

431útiles de eventos basadas en claves, los procesadores de eventos
que responden al evento deben consultar una base de datos para
recuperar la información que necesitan para procesar el evento.
Cuando un cliente realiza un pedido, el procesador de eventos Order
Placement (Colocación de Pedidos) inserta el pedido en la base de
datos y activa un evento basado en claves llamado order_placed
(pedido_realizado). Este evento contiene un único valor de clave
con el ID del pedido en un JSON simple:

{
 "order_id": "123"
}

Una de las principales desventajas de las cargas útiles de eventos
basadas en claves es que cada procesador de eventos que responde
al evento debe consultar la base de datos para obtener la
información que necesita para procesar el pedido. Por ejemplo,
cuando el procesador de eventos Payment (Pago) responde al
evento, debe consultar la base de datos para obtener la información
del pedido que necesita para procesar el pago. El procesador de
eventos Inventory (Inventario) también responde
simultáneamente al evento, por lo que también debe consultar la
base de datos para recuperar el ID del artículo y la cantidad. Esto
puede restar capacidad de respuesta, rendimiento y escalabilidad, y
puede saturar una base de datos, particularmente en una
arquitectura altamente paralela y asíncrona como la arquitectura
orientada a eventos. (Consulta “Topologías de datos” para conocer
formas de mitigar este riesgo). Las cargas útiles de eventos basadas
en claves también presentan un desafío si los datos requeridos no
son fácilmente accesibles (por ejemplo, si se encuentran dentro del
contexto delimitado de otro procesador de eventos). La Figura 15-12
ilustra esta técnica.

432Este diagrama ilustra el funcionamiento de las cargas útiles de eventos basadas en

claves dentro de una arquitectura de software. El proceso comienza con el servicio

de colocación de pedidos, el cual se encarga de insertar el pedido en una base de

datos centralizada y, simultáneamente, envía una notificación a través de un canal

de comunicación. En este modelo, se especifica que solo el identificador del pedido

está en la carga útil del evento, lo que simplifica el mensaje inicial pero requiere

pasos adicionales para los receptores. El flujo continúa hacia el servicio de pagos y

el servicio de inventario, los cuales reciben la notificación mínima; por lo tanto, se

indica  que  los  procesadores  de  eventos  deben  consultar  la  base  de  datos  para

recuperar  los  datos  necesarios  para  el  procesamiento.  De  esta  manera,  cada

componente  obtiene  la  información  completa  directamente  del  almacenamiento

para ejecutar sus tareas correspondientes. (Accesibilidad de la imagen)

Figura 15-12. Con las cargas útiles de eventos basadas en claves, solo la clave de
contexto está contenida en el evento

Sin embargo, el uso de cargas útiles de eventos basadas en claves
conlleva muchas ventajas, algunas de las cuales pueden superar los
problemas de rendimiento y escalabilidad. La primera gran ventaja
es una mejor consistencia e integridad de los datos en general,
gracias a que se tiene un único sistema de registro. Debido a que los
datos sobre el evento se encuentran en un solo lugar (la base de
datos), las cargas útiles de eventos basadas en claves pueden
manejar los cambios en los datos durante el procesamiento del
evento mucho más fácilmente que las cargas útiles de eventos
basadas en datos.

433La segunda ventaja principal es que, dado que el contrato en las
cargas útiles de eventos basadas en claves es tan simple y rara vez
cambia, los arquitectos suelen implementarlo mediante JSON o XML
flexible y sin esquema. Por lo tanto, las cargas útiles de eventos
basadas en claves no tienen los mismos problemas con la gestión de
cambios de contrato, el versionado y las estrategias de comunicación
y obsolescencia que suelen tener las cargas útiles de eventos
basadas en datos.

Otra ventaja de las cargas útiles de eventos basadas en claves: no
tienen los mismos problemas de acoplamiento de marca y ancho de
banda que las cargas útiles de eventos basadas en datos. Debido a
que no hay datos opacos asociados con el evento, los contratos son
simples, pequeños y utilizan un ancho de banda mínimo. Por lo
tanto, tienden a funcionar más rápido, desde la perspectiva de la red
y el agente de mensajes (message broker), que las cargas útiles de
eventos basadas en datos.

Resumen de compensaciones

Elegir entre una carga útil de evento basada en datos frente a una
carga útil basada en claves requiere un análisis cuidadoso de las
compensaciones (trade-offs). Recuerda que no es una propuesta de
todo o nada: cada tipo de evento puede utilizar un tipo de carga útil
diferente. La Tabla 15-1 resume las compensaciones asociadas con
las cargas útiles de eventos basadas en datos y basadas en claves.

434Tabla 15-1. Cargas útiles de eventos basadas en datos versus
basadas en claves

Criterio

Rendimiento y
escalabilidad

Cargas útiles
basadas en datos

Cargas útiles
basadas en claves

Bueno

Malo

Gestión de contratos Malo

Acoplamiento de
marca

Malo

Utilización de ancho
de banda

Malo

Acceso restringido a
la base de datos

Bueno

Fragilidad general
del sistema

Mala

Bueno

Bueno

Bueno

Malo

Buena

Nota que la compensación general entre estas dos opciones se
reduce a la escalabilidad y el rendimiento frente a la gestión de
contratos y la utilización del ancho de banda. Pregúntate cuál es
más importante para cada evento en particular. Algunos
procesamientos de eventos requieren niveles extremos de escala y
rendimiento, en cuyo caso una carga útil de evento basada en datos
sería una mejor opción; algunos datos de procesamiento de eventos
sufrirán cambios frecuentes, en cuyo caso una carga útil de evento
basada en claves podría ser más apropiada.

435Como ocurre con la mayoría de las cosas en la arquitectura de
software, las elecciones de los arquitectos se sitúan en un espectro,
no en una simple opción binaria. Por eso es importante tener
cuidado de evitar activar lo que se conoce como eventos anémicos.

Eventos anémicos

Un evento anémico es un evento derivado con una carga útil que no
contiene suficiente información para ayudar al procesador de
eventos a tomar decisiones y carece del contexto necesario para el
procesamiento posterior.

La Figura 15-13 ilustra un evento derivado anémico. En este
ejemplo, un cliente ha actualizado cierta información en su perfil de
usuario. Una vez que esa información se actualiza en la base de
datos, el procesador de eventos Customer Profile (Perfil del
Cliente) activa un evento profile_updated (perfil_actualizado),
utilizando una carga útil de evento basada en claves que pasa solo el
ID del cliente como sus datos basados en claves.

Los tres servicios que responden a este evento reciben solo el ID del
cliente y el contexto de que se cambió el perfil del cliente. El primer
servicio (Service 1) no tiene idea de qué datos se cambiaron en el
perfil: ¿nombre, dirección, alguna otra información crítica?
Desafortunadamente, consultar la base de datos no puede
responder a esta pregunta, por lo que el Service 1 no tiene idea de
cómo responder o qué acción tomar. El Service 2 responde al
evento profile_updated (perfil_actualizado), pero guiándose
solo por la clave, no sabe si necesita realizar algún procesamiento
adicional. Finalmente, el Service 3 responde al mismo evento, pero
no tiene idea de cuáles eran los valores anteriores y, por lo tanto, no
puede realizar su procesamiento. Los tres procesadores de eventos
necesitan responder de alguna manera a la actualización del perfil
por parte del cliente, pero no pueden debido a la falta de
información. Estos son eventos anémicos: eventos que no incluyen
información adicional para procesar más el evento.

436Esta  imagen  ilustra  el  concepto  de  un  evento  anémico  dentro  de  un  flujo  de

arquitectura de software. El proceso comienza cuando un usuario interactúa con el

servicio  de  perfil  de  cliente,  el  cual  genera  un  evento  de  perfil  actualizado;  sin

embargo,  una  nota  especifica  que  este  evento  solo  contiene  el  identificador  del

cliente,  careciendo  de  contexto  suficiente.  Esta

falta  de  datos  provoca

incertidumbre  en  los  componentes  receptores:  el  servicio  uno  se  pregunta  qué

datos  cambiaron,  el  servicio  dos  no  sabe  si  necesita  responder  y  el  servicio  tres

desconoce  cuáles  son  los  valores  anteriores,  demostrando  cómo  un  mensaje  con

información insuficiente dificulta que los servicios dependientes realicen sus tareas

de manera efectiva. (Accesibilidad de la imagen)

Figura 15-13. Un evento anémico carece de contexto suficiente para procesar el
evento

Para evitar eventos anémicos como este, incluye la información
actualizada del cliente así como los valores anteriores, ya que la
mayoría de las bases de datos normalmente no reflejan esa
información.

Este es un ejemplo del espectro de la granularidad de la carga útil
de los eventos. En el extremo izquierdo del espectro se encuentran
las cargas útiles de eventos basadas en claves, donde solo la clave
está contenida en el evento. Aunque esto tiene mérito al crear o
eliminar un pedido, no funciona bien cuando un cliente actualiza un
pedido. En el extremo derecho del espectro está la carga útil de
eventos basada en datos, donde se incluye toda la información, sea

437necesaria o no. Aquí es donde el acoplamiento de marca muestra su
peor cara. El escenario de actualización del perfil del cliente encaja
en algún punto entre estos extremos porque proporciona el nivel
correcto de información, evitando así el problema de los eventos
derivados anémicos.

El antipatrón Enjambre de mosquitos (Swarm
of Gnats)

Relacionado con los eventos anémicos hay un antipatrón conocido
como el Enjambre de mosquitos (Swarm of Gnats). Probablemente
conozcas a los mosquitos como esos insectos voladores muy
pequeños y molestos que zumban alrededor de tu cabeza,
fastidiándote lo suficiente como para obligarte a volver a casa en un
hermoso día soleado. Mientras que los eventos anémicos se
preocupan por la granularidad de la carga útil de un evento, el
antipatrón Enjambre de mosquitos se preocupa por la granularidad
de los eventos activados en sí mismos y por cuántos eventos
derivados se activan desde un procesador de eventos. Si un
arquitecto activa demasiados eventos derivados desde un solo
procesador de eventos, corre el riesgo de quedar atrapado en el
antipatrón Enjambre de mosquitos.

Considera el ejemplo del pago con tarjeta de crédito que se muestra
en la Figura 15-14, donde un cliente realiza un pedido y se le cobra
a su tarjeta de crédito para pagarlo. Cuando se realiza el cargo a la
tarjeta, el procesador de eventos Payment (Pago) activa un evento
payment applied (pago aplicado), y (afortunadamente) el
procesador de eventos Fraud Detection (Detección de Fraude) lo
escucha. Este procesador de eventos analiza cada cargo para
determinar si es legítimo o fraudulento. Independientemente del
resultado, el procesador de eventos Fraud Detection activa un
evento derivado fraud_checked (fraude_verificado) con el

438resultado de la verificación de fraude contenido en la carga útil del
evento.

Este diagrama ilustra un flujo de trabajo en una arquitectura orientada a eventos

donde se observa un ejemplo de eventos con una granularidad demasiado gruesa.

El proceso comienza con el servicio de colocación de pedidos, que activa el evento

de pedido realizado, el cual es recibido por el servicio de pagos. Una vez que este

servicio termina su tarea, genera el evento de pago aplicado, que llega al servicio

de detección de fraude. Tras procesar la información, este último emite el evento

de fraude verificado. Finalmente, dicho evento se ramifica hacia tres componentes

distintos:  el  bloqueo  de  tarjeta  de  crédito,  la  notificación  al  cliente  y  el  perfil  de

compra. Estos tres elementos aparecen marcados con signos de interrogación, lo

que  indica  que  cada  uno  debe  analizar  el  contenido  del  evento  para  decidir  si  le

corresponde  actuar  o  no,  evidenciando  la  ineficiencia  de  enviar  un  único  evento

general para distintas acciones potenciales. (Accesibilidad de la imagen)

Figura 15-14. Un ejemplo de un evento que es demasiado de grano grueso
(coarse-grained)

Tres procesadores de eventos están interesados en el resultado de la
verificación de fraude de la tarjeta de crédito:

439Si se detecta fraude, el procesador de eventos Credit Card
Locking (Bloqueo de Tarjeta de Crédito) bloquea la
tarjeta de crédito del cliente para evitar cargos adicionales.

El procesador de eventos Customer Notify (Notificación
al Cliente) notifica al cliente sobre el posible fraude.

Si no se detecta fraude, el procesador de eventos Purchase
Profile (Perfil de Compra) actualiza sus algoritmos.

Desafortunadamente, cuando se activa un único evento derivado
fraud_checked, todos estos procesadores de eventos deben
responder al evento, revisar la carga útil para ver el resultado y
decidir si toman medidas. Debido a que este evento derivado es
demasiado de grano grueso, todos los procesadores de eventos
deben realizar un procesamiento adicional: analizar la carga útil del
único evento derivado para decidir si actúan. Si no se ha detectado
ningún fraude, esto es un desperdicio de ancho de banda y potencia
de procesamiento, ya que solo el procesador de eventos Purchase
Profile necesitaba tomar alguna medida.

Un enfoque mucho más eficiente sería activar dos eventos derivados
separados (fraud_detected (fraude_detectado) y
no_fraud_detected (no_se_detectó_fraude)), como se muestra en
la Figura 15-15. Aquí, los eventos derivados activados por el
procesador de eventos Fraud Detection (Detección de Fraude)
proporcionan contexto fuera de la carga útil del evento, permitiendo
que cada procesador de eventos decida si responder sin tener que
analizar la carga útil interna del evento.

440Este  diagrama  ilustra  un  flujo  de  trabajo  dentro  de  una  arquitectura  dirigida  por

eventos,  comenzando  con  el  Servicio  de  realización  de  pedidos  que  genera  el

evento de Pedido realizado. Este evento es recibido por el Servicio de pago, el cual

activa la notificación de Pago aplicado para que el Servicio de detección de fraude

procese  la  transacción.  Dependiendo  del  resultado  de  este  análisis,  el  flujo  se

bifurca: si se emite el evento de Fraude detectado, se activan de forma paralela el

Bloqueo de tarjeta de crédito y la Notificación al cliente; en cambio, si se genera el

evento de Fraude no detectado, la información se dirige hacia la actualización del

Perfil de compra. (Accesibilidad de la imagen)

Figura 15-15. Activar múltiples eventos permite un procesamiento y una toma de
decisiones más eficientes

En este ejemplo, activar múltiples eventos derivados para cada
resultado permite un mejor flujo de eventos, menos rotación y un
procesamiento más eficiente. Sin embargo, activar demasiados
eventos derivados da como resultado el antipatrón Enjambre de
mosquitos (Swarm of Gnats).

El escenario mostrado en la Figura 15-16 ilustra cómo puede ocurrir
este antipatrón. Un cliente se ha mudado recientemente y necesita

441cambiar su perfil de usuario en el sitio web para actualizar la
dirección de facturación de su tarjeta de crédito, la dirección de
envío (donde se enviarán los pedidos) y el número de teléfono,
pasando de su antiguo teléfono fijo a su teléfono celular. Cuando el
cliente hace clic en el botón "Enviar" para estos cambios de perfil, el
procesador de eventos Customer Profile (Perfil del Cliente)
recibe la solicitud de actualización, actualiza la base de datos y
activa un evento separado por cada actualización que contenga la
información necesaria para realizar cualquier procesamiento
posterior.

Esta  imagen  ilustra  un  flujo  de  datos  en  el  que  un  usuario  interactúa  con  un

servicio de perfil de cliente, el cual desencadena tres eventos distintos: facturación

actualizada,  dirección  de  envío  actualizada  y  teléfono  actualizado.  Una  nota  a  la

derecha  advierte  que  estos  eventos  son  demasiado  granulares,  señalando  que

este  nivel  de  detalle  excesivo  puede  saturar  el  sistema.  La  ilustración  muestra

cómo  una  sola  acción  del  usuario  se  fragmenta  en  múltiples  notificaciones

pequeñas  en  lugar  de  consolidarse  en  un  único  evento  de  actualización  más

eficiente. (Accesibilidad de la imagen)

Figura 15-16. Activar demasiados eventos derivados de grano fino (fine-grained)
se conoce como el antipatrón Enjambre de mosquitos (Swarm of Gnats)

El problema de activar demasiados eventos detallados de grano fino
(fine-grained) es que puede saturar y abrumar al sistema con

442eventos derivados todos relacionados con lo mismo: el cliente
actualizó su perfil de usuario. Este antipatrón también tiende a
proliferar numerosos eventos derivados pequeños de otros
procesadores de eventos, haciendo que con el tiempo sea difícil para
cualquiera entender los flujos generales de eventos del sistema.

Para evitar este antipatrón, el arquitecto podría agrupar cada
actualización de perfil individual en un único evento derivado
profile_updated (perfil_actualizado) para la acción completa,
que contenga los datos de antes y después de todos los campos
actualizados. Este enfoque más eficiente se ilustra en la Figura 15-
17.

El diagrama muestra el flujo de una operación donde un usuario interactúa con el

servicio  de  perfil  de  cliente.  Este  componente  genera  un  evento  de  perfil

actualizado,  el  cual,  según  señala  el  texto  adjunto,  es  un  evento  único  que

contiene  todas  las  actualizaciones  del  perfil  de  usuario,  permitiendo  agrupar  los

cambios en un solo mensaje para su procesamiento posterior. (Accesibilidad de la

imagen)

Figura 15-17. Combinar cambios de estado individuales en un solo evento derivado
evita el antipatrón Enjambre de mosquitos (Swarm of Gnats)

Determinar el nivel correcto de granularidad para los eventos
derivados puede ser bastante desafiante. Recomendamos centrarse
en el resultado del procesamiento o del cambio de estado para evitar
el antipatrón Enjambre de mosquitos (Swarm of Gnats) y ayudar a
simplificar los flujos de eventos.

443Manejo de errores

El patrón Workflow Event (Evento de Flujo de Trabajo) de la
arquitectura reactiva es una forma de abordar el manejo de errores
en un flujo de trabajo asíncrono. Este patrón aborda tanto la
resiliencia como la capacidad de respuesta, ya que permite que el
sistema maneje errores asíncronos sin afectar su capacidad de
respuesta.

El patrón Workflow Event aprovecha la delegación, la contención y la
reparación mediante el uso de un workflow delegate (delegado de
flujo de trabajo), como se ilustra en la Figura 15-18. En este patrón,
un procesador de eventos pasa datos de forma asíncrona a través de
un canal de mensajes al consumidor de eventos. Si el consumidor de
eventos experimenta un error al procesar los datos, delega
inmediatamente ese error al servicio Workflow Processor
(Procesador de Flujo de Trabajo) y pasa al siguiente mensaje en
la cola de eventos. De esta manera, el siguiente mensaje se procesa
inmediatamente, por lo que la capacidad de respuesta general sigue
siendo la misma. Si el consumidor de eventos dedicara tiempo a
intentar descifrar el error, no estaría procesando el siguiente
mensaje en la cola, retrasando no solo el siguiente mensaje, sino
todos los demás mensajes que esperan en la cola de procesamiento.
Cuando el servicio Workflow Processor (Procesador de Flujo de
Trabajo) recibe un error, intenta averiguar qué falla con el mensaje.
¿Tal vez hay un error estático y determinista? Podría analizar el
mensaje utilizando algunos algoritmos de aprendizaje automático o
IA para buscar alguna anomalía en los datos. De cualquier manera,
el procesador de flujo de trabajo realiza cambios en los datos
originales programáticamente (es decir, sin intervención humana)
para intentar repararlos y luego los envía de vuelta a la cola de
origen. El consumidor de eventos ve este mensaje actualizado como
uno nuevo e intenta procesarlo de nuevo, con suerte esta vez con
más éxito.

444Por supuesto, el procesador de flujo de trabajo no siempre puede
determinar qué está mal con el mensaje. En estos casos, envía el
mensaje a otra cola, que es recibida por un tablero en el escritorio
de una persona con los conocimientos necesarios. Esta persona mira
el mensaje, aplica correcciones manuales y luego lo vuelve a enviar
a la cola original (normalmente a través de una variable de
encabezado de mensaje "reply-to").

Este diagrama representa el patrón de eventos de flujo de trabajo, donde puedes

observar cómo un productor de eventos envía un mensaje a través de un canal de

eventos  hacia  un  consumidor  de  eventos.  Ante  un  error  en  el  procesamiento,  el

consumidor  delega  la  tarea  mediante  otro  canal  de  eventos  a  un  procesador  de

flujos  de  trabajo,  el  cual  tiene  la  capacidad  de  reparar  el  evento  y  devolverlo  al

canal  original  o  enviarlo  a  un  panel  de  control.  En  esta  etapa  final,  una  persona

revisa la información en el panel de control para aplicar correcciones manuales y

reenviar  el  evento  corregido  nuevamente  al  primer  canal  de  eventos  para  que  el

ciclo continúe de forma exitosa. (Accesibilidad de la imagen)

Figura 15-18. El patrón Workflow Event (Evento de Flujo de Trabajo) de la
arquitectura reactiva

445Supongamos que un asesor de trading en una parte del país acepta
trade orders (órdenes de comercio) (instrucciones sobre qué
acciones comprar y cuántas participaciones) en nombre de una gran
firma de trading en otra parte del país. El asesor agrupa las órdenes
de comercio en lo que suele llamarse un basket (canasta) y las envía
de forma asíncrona a un corredor en otra parte del país, quien luego
compra las acciones. Para simplificar el ejemplo, supongamos que el
contrato para las instrucciones de comercio debe cumplir con lo
siguiente:

ACCOUNT(Cadena),SIDE(Cadena),SYMBOL(Cadena),SHARES(EnteroLargo)

Supongamos que la gran firma de trading recibe la siguiente canasta
de órdenes de comercio de Apple (AAPL) del asesor de trading:

12654A87FR4,BUY,AAPL,1254
87R54E3068U,BUY,AAPL,3122
6R4NB7609JJ,BUY,AAPL,5433
2WE35HF6DHF,BUY,AAPL,8756 SHARES
764980974R2,BUY,AAPL,1211
1533G658HD8,BUY,AAPL,2654

La cuarta instrucción de comercio (2WE35HF6DHF,BUY,AAPL,8756
SHARES) tiene la palabra SHARES después del número de acciones
para la transacción. Cuando la firma principal procesa estas órdenes
de comercio asíncronas sin ninguna capacidad de manejo de errores,
ocurre el siguiente error dentro del servicio TradePlacement:

Excepción en el hilo "main" java.lang.NumberFormatException:

Para la cadena de entrada: "8756 SHARES"
at java.lang.NumberFormatException.forInputString
(NumberFormatException.java:65)
at java.lang.Long.parseLong(Long.java:589)
at java.lang.Long.<init>(Long.java:965)
at trading.TradePlacement.execute(TradePlacement.java:23)
at trading.TradePlacement.main(TradePlacement.java:29)

446Cuando ocurre esta excepción, debido a que se trató de una solicitud
asíncrona, no hay un usuario al que responder sincrónicamente y
corregir el error. El servicio TradePlacement no puede hacer nada,
excepto posiblemente registrar la condición de error.

Aplicar el patrón Workflow Event puede corregir este error
programáticamente. Dado que la firma principal no tiene control
sobre el asesor de trading ni sobre los datos de las órdenes de
comercio que envía, debe reaccionar para corregir el error por sí
misma (ver Figura 15-19). Cuando ocurre el mismo error
(2WE35HF6DHF,BUY,AAPL,8756 SHARES), el servicio TradePlacement
delega inmediatamente el error a través de mensajería asíncrona al
servicio Trade Placement Error (Error de Colocación de
Operación) para su manejo, enviándolo junto con la información del
error sobre la excepción:

Operación Colocada: 12654A87FR4,BUY,AAPL,1254
Operación Colocada: 87R54E3068U,BUY,AAPL,3122
Operación Colocada: 6R4NB7609JJ,BUY,AAPL,5433
Error al Colocar Operación: "2WE35HF6DHF,BUY,AAPL,8756 SHARES"
Enviando al procesador de errores de operación <-- delegar la
corrección del error y continuar
Operación Colocada: 764980974R2,BUY,AAPL,1211
...

El servicio Trade Placement Error, actuando como el delegado del
flujo de trabajo, recibe el error e inspecciona la excepción. Al ver
que el problema es con la palabra SHARES en el campo de Número de
Acciones, el servicio Trade Placement Error elimina la palabra
SHARES y vuelve a enviar la operación para su reprocesamiento:

Error de Orden de Operación Recibido: 2WE35HF6DHF,BUY,AAPL,8756 SHARES
Operación corregida: 2WE35HF6DHF,BUY,AAPL,8756
Volviendo a enviar Operación para Reprocesamiento

El servicio TradePlacement ahora puede procesar la operación
corregida con éxito:

447...
operación colocada: 1533G658HD8,BUY,AAPL,2654
operación colocada: 2WE35HF6DHF,BUY,AAPL,8756 <-- esta era la
operación original con error

Esta ilustración detalla el manejo de errores mediante el patrón de evento de flujo

de trabajo en una arquitectura distribuida. El diagrama muestra un proceso de seis

pasos  que  comienza  cuando  un  asesor  de  inversiones  envía  una  transacción  de

forma asíncrona a través de un canal de eventos hacia el servicio de colocación de

transacciones. En el segundo punto, el servicio identifica una transacción errónea

y, en el tercer paso, la envía a una cola de mensajes. El cuarto paso consiste en

que un procesador de flujo de trabajo recibe el mensaje y corrige la transacción;

posteriormente,  en  el  quinto  paso,  envía  esta  transacción  corregida  de  vuelta  al

canal  de  eventos  original.  Finalmente,  en  el  sexto  paso,  el  servicio  de  colocación

de  transacciones  procesa  con  éxito  la  transacción  ya  corregida.  El  flujo  visual

destaca  cómo  los  mensajes  viajan  entre  los  componentes,  permitiendo  que  el

sistema mantenga su operatividad y capacidad de respuesta a pesar de encontrar

errores en los datos iniciales. (Accesibilidad de la imagen)

Figura 15-19. Manejo de errores con el patrón Workflow Event

448Una consecuencia de usar el patrón Workflow Event es que los
mensajes que se envían a un procesador de flujo de trabajo y luego
se vuelven a enviar se procesan fuera de secuencia. En nuestro
ejemplo de trading, el orden de los mensajes importa, porque todas
las operaciones dentro de una cuenta determinada deben procesarse
en orden (por ejemplo, una SELL (VENTA) de IBM debe ocurrir antes
de una BUY (COMPRA) de AAPL dentro de la misma cuenta de
corretaje). Sería complejo, aunque no imposible, mantener el orden
de los mensajes dentro de un contexto dado (en este caso, el
número de cuenta de corretaje). Una forma de abordar esto es que
el servicio TradePlacement ponga en cola y almacene el número de
cuenta de corretaje de la operación errónea. Cualquier operación
con ese mismo número de cuenta de corretaje se almacenaría en
una cola temporal para su procesamiento posterior (en orden de
primero en entrar, primero en salir o FIFO). Una vez que la
operación errónea se corrige y se procesa, el servicio
TradePlacement saca de la cola las operaciones restantes para esa
misma cuenta y las procesa en orden.

Previniendo la pérdida de datos

Los arquitectos que lidian con comunicaciones asíncronas siempre
están preocupados por la pérdida de datos: cuando un evento o
mensaje se pierde o nunca llega a su destino final.
Afortunadamente, existen técnicas básicas listas para usar que
previenen la pérdida de datos.

Los arquitectos pueden implementar canales de eventos de diversas
maneras. La mayoría de las arquitecturas orientadas a eventos
utilizan el Advanced Message Queuing Protocol (AMQP) para activar
y responder a eventos. Ejemplos de brokers AMQP incluyen Amazon
SNS (Simple Notification Service), RabbitMQ, Solace y Azure Event
Hubs. Con AMQP, los eventos se publican en un exchange. El
exchange utiliza las reglas de vinculación (binding) establecidas por
los procesadores de eventos consumidores para reenviar el evento a

449una cola para cada procesador de eventos que se suscribe a ese
evento. Los brokers AMQP también pueden aprovechar lo que se
conoce como el patrón Event Forwarding (Reenvío de Eventos) para
prevenir la pérdida de datos, una técnica que describimos en esta
sección.

Otra implementación de canal de eventos es la Jakarta Messaging
API (anteriormente Java Message Service o JMS), que utiliza topics
(temas) en lugar del proceso de reenvío de dos pasos que usan las
colas. No obstante, Jakarta Messaging todavía puede aprovechar el
patrón Event Forwarding para evitar la pérdida de datos, siempre
que los procesadores de eventos que responden a un evento estén
configurados como suscriptores duraderos. Un durable subscriber
(suscriptor duradero) es aquel al que se le garantiza la recepción de
un evento. Si el procesador de eventos está caído o no está
disponible por cualquier otra razón, el topic de JMS almacena el
evento hasta que el procesador de eventos suscrito vuelva a estar
disponible.

Otra posible implementación de canal de eventos es el streaming de
eventos usando Kafka como un event broker (intermediario de
eventos) (el producto de software que contiene las colas y los
temas). Las técnicas para prevenir la pérdida de datos dentro del
streaming de eventos son muy diferentes de las utilizadas para el
patrón Event Forwarding descrito en esta sección. Consulta el sitio
web de Kafka para obtener más información sobre cómo prevenir la
pérdida de datos al usar este tipo de intermediario de eventos de
streaming.
Considera un escenario típico en el que el procesador de eventos A
publica de forma asíncrona un evento en un broker de mensajería, el
cual finalmente va a una cola AMQP o a un tema JMS. El procesador
de eventos B responde al evento e inserta los datos de la carga útil
en una base de datos. Como se ilustra en la Figura 15-20, hay tres
formas en que puede ocurrir la pérdida de datos en este escenario:

4501. Mientras el procesador de eventos A publica el evento, este

se bloquea antes de que se pueda enviar un acuse de recibo
desde el broker de eventos; alternativamente, el broker de
eventos envía un acuse de recibo al procesador de eventos
A, pero luego se bloquea antes de que el evento sea
aceptado por otro procesador de eventos.

2. El procesador de eventos B acepta el evento de la cola pero

se bloquea antes de poder procesarlo.

3. El procesador de eventos B no puede persistir el mensaje en

la base de datos debido a un error de datos.

Cada una de estas áreas de pérdida de datos se puede mitigar
mediante el patrón Event Forwarding.

Esta  imagen  muestra  un  flujo  de  trabajo  técnico  donde  puedes  identificar  los

puntos críticos propensos a fallos. El diagrama presenta al Procesador de eventos

A,  compuesto  por  varios  componentes,  enviando  información  hacia  un  canal  de

eventos.  Posteriormente,  este  mensaje  llega  al  Procesador  de  eventos  B,  que

también  cuenta  con  sus  propios  componentes,  para  terminar  almacenando  los

resultados  en  una  base  de  datos.  A  lo  largo  de  este  trayecto,  se  señalan  con

cruces rojas tres oportunidades de pérdida de datos numeradas: la primera ocurre

al intentar enviar el evento al canal, la segunda sucede cuando el mensaje sale del

canal hacia el siguiente procesador y la tercera se manifiesta durante el intento de

guardar la información en la base de datos. (Accesibilidad de la imagen)

Figura 15-20. Lugares donde puede ocurrir la pérdida de datos dentro de una
arquitectura orientada a eventos

451Con el primer problema, el evento nunca llega a la cola o el broker
falla antes de que el evento sea leído. Para abordar esto, usa colas
de mensajes persistentes junto con envío síncrono. Las colas de
mensajes persistentes admiten guaranteed delivery (entrega
garantizada): cuando el broker de eventos recibe el evento, no solo
lo almacena en memoria para una recuperación rápida, sino que
también lo persiste en algún tipo de almacén de datos físico (como
un sistema de archivos o una base de datos). Si el broker de eventos
se cae, el evento está almacenado físicamente en el disco, por lo
que seguirá estando disponible para su procesamiento cuando el
broker de eventos vuelva a estar en línea. El synchronous send
(envío síncrono) realiza una espera bloqueante en el procesador de
eventos, impidiéndole activar el evento hasta que el broker confirme
que ha persistido el evento en la base de datos. Estas dos técnicas
básicas previenen la pérdida de datos entre el productor de eventos
y la cola, porque el evento todavía está con el productor de eventos
o está persistido dentro de la cola.

Una técnica de mensajería básica llamada client acknowledge mode
(modo de confirmación del cliente) puede abordar el segundo
problema, donde el procesador de eventos B saca de la cola el
siguiente evento disponible y se bloquea antes de poder procesarlo.
Por defecto, cuando un evento se lee de una cola, se elimina
inmediatamente de esa cola (esto se llama modo auto
acknowledge). El modo "client acknowledge" mantiene el evento en
la cola y le adjunta el ID del cliente para que ningún otro
consumidor pueda leer o procesar el evento. Con este modo, si el
procesador de eventos B se bloquea, el evento sigue preservado en
la cola, evitando la pérdida del mensaje.
El tercer problema, en el que el procesador de eventos B no puede
persistir el evento en la base de datos debido a algún error de datos,
puede abordarse con transacciones ACID a través de un commit de
base de datos. Una vez que el procesador de eventos emite un
commit de base de datos, se garantiza que los datos se persistirán

452en la base de datos. El Last participant support (Soporte al último
participante - LPS) elimina el evento de la cola persistida al
confirmar que todo el procesamiento se ha completado y que el
evento ha sido persistido. Esto garantiza que el evento no se haya
perdido en tránsito desde el procesador de eventos A hasta la base
de datos. Estas técnicas se ilustran en la Figura 15-21.

Este diagrama ilustra las técnicas fundamentales para prevenir la pérdida de datos

dentro de una arquitectura dirigida por eventos, detallando un flujo que comienza

en  el  procesador  de  eventos  A.  En  la  primera  etapa,  los  componentes  de  este

procesador realizan un envío síncrono hacia un canal de eventos que utiliza colas

persistentes  para  garantizar  que  el  mensaje  se  almacene  físicamente.  En  el

segundo  punto,  el  procesador  de  eventos  B  recibe  la  información  empleando  el

modo de reconocimiento del cliente, lo que asegura que el evento permanezca en

la cola hasta que se procese con éxito. Finalmente, en el tercer paso, se utiliza el

soporte  del  último  participante  para  persistir  los  datos  en  una  base  de  datos,

protegiendo la integridad de la información mediante transacciones de atomicidad,

consistencia, aislamiento y durabilidad. (Accesibilidad de la imagen)

Figura 15-21. Previniendo la pérdida de datos dentro de una arquitectura
orientada a eventos

Procesamiento de solicitud-respuesta

Hasta ahora en este capítulo, hemos tratado con solicitudes
asíncronas que no necesitan una respuesta inmediata del

453consumidor del evento. Pero ¿qué pasa con los procesadores de
eventos que necesitan información de vuelta inmediatamente de
otro procesador de eventos; por ejemplo, esperar algún tipo de ID
de confirmación o acuse de recibo antes de activar un evento? Este
escenario requiere comunicación síncrona para completar la
solicitud.

En EDA, la comunicación síncrona se logra típicamente a través de
mensajería request-reply (solicitud-respuesta) (a veces denominada
comunicaciones pseudosíncronas). Cada canal de eventos dentro de
la mensajería de solicitud-respuesta consta de dos colas: una cola de
request (solicitud) y una cola de reply (respuesta). El productor del
mensaje que realiza la solicitud inicial de información envía datos de
forma asíncrona a la cola de solicitud y luego devuelve el control al
productor del mensaje. El productor del mensaje realiza entonces un
procesamiento adicional y, finalmente, espera en la cola de
respuesta por la contestación. El consumidor del mensaje recibe y
procesa el mensaje, luego envía la respuesta a la cola de respuesta.
El productor del evento recibe el mensaje con los datos de
respuesta. Este flujo básico se ilustra en la Figura 15-22.

454Este  diagrama  ilustra  el  procesamiento  de  mensajes  mediante  el  modelo  de

solicitud-respuesta  entre  un  productor  de  eventos  y  un  consumidor  de  eventos,

ambos  integrados  por  diversos  componentes.  El  flujo  comienza  cuando  el

productor  envía  una  señal  a  la  cola  de  peticiones;  en  ese  instante,  el  control  se

devuelve  al  productor  una  vez  que  se  realiza  la  solicitud  a  dicha  cola,

permitiéndote continuar con otras tareas mientras se activa una señal de espera.

Por  su  parte,  el  consumidor  procesa  el  requerimiento  y  envía  la  contestación  a

través de una cola de respuestas. El proceso concluye cuando el productor realiza

una espera bloqueante hasta que se reciba el mensaje de respuesta, asegurando

así la sincronización final de la comunicación. (Accesibilidad de la imagen)

Figura 15-22. Procesamiento de mensajes de solicitud-respuesta

Hay dos formas principales de implementar la mensajería de
solicitud-respuesta. La primera técnica (y la más común) es poner
un campo correlation ID (ID de correlación - CID) en el encabezado
del mensaje de respuesta, generalmente configurado con el ID de
mensaje del mensaje de solicitud original (simplemente llamado ID
en la Figura 15-23). Funciona de esta manera:

4551. El productor de eventos envía un mensaje a la cola de

solicitud y registra el ID de mensaje único (ID 124). Observa
que el CID en este caso es null.

2. El productor de eventos realiza una espera bloqueante en la
cola de respuesta con un filtro de mensaje (también llamado
message selector), donde el CID en el encabezado del
mensaje es igual al ID del mensaje original (124). Hay dos
mensajes en la cola de respuesta: ID 855 con CID 120, e ID
856 con CID 122. Ninguno de estos mensajes se recogerá,
porque ningún ID de correlación coincide con lo que busca el
consumidor de eventos (CID 124).

3. El consumidor de eventos recibe el mensaje (ID 124) y

procesa la solicitud.

4. El consumidor de eventos crea el mensaje de respuesta que
contiene la contestación y establece el CID en el encabezado
del mensaje con el ID del mensaje original (124).

5. El consumidor de eventos envía el nuevo ID de mensaje

(857) a la cola de respuesta.

6. El productor de eventos recibe el mensaje, porque el CID
(124) coincide con el selector de mensajes del paso 2.

456Este  diagrama  detalla  el  funcionamiento  del  procesamiento  de  mensajes  de

solicitud  y  respuesta  utilizando  un  identificador  de  correlación  dentro  de  una

arquitectura  orientada  a  eventos.  En  la  parte  izquierda,  el  productor  de  eventos

inicia  el  flujo  enviando  un  mensaje  a  la  cola  de  solicitudes  con  el  identificador

ciento veinticuatro y un identificador de correlación marcado como nulo. Al mismo

tiempo, el productor se queda en un estado de espera activa, buscando en la cola

de respuestas cualquier mensaje donde el identificador de correlación coincida con

el número ciento veinticuatro. A la derecha, el consumidor de eventos procesa la

entrada y genera una respuesta con el identificador ochocientos cincuenta y siete,

asegurándose de incluir el identificador de correlación ciento veinticuatro para que

el sistema pueda rastrearlo. Finalmente, el mensaje de respuesta pasa por la cola

de respuestas, donde se diferencia de otros mensajes con correlaciones distintas,

hasta que el productor lo recibe con éxito. (Accesibilidad de la imagen)

Figura 15-23. Procesamiento de mensajes de solicitud-respuesta usando un ID de
correlación

La otra forma de implementar la mensajería de solicitud-respuesta
es usar una temporary queue (cola temporal) para la cola de
respuesta. Una cola temporal está dedicada a una solicitud
específica, se crea cuando se realiza la solicitud y se elimina cuando

457la solicitud termina. Esta técnica, como se ilustra en la Figura 15-24,
no requiere un ID de correlación, porque la cola temporal es una
cola dedicada solo conocida por el productor de eventos para esa
solicitud específica. La técnica de la cola temporal funciona de la
siguiente manera:

1. El productor de eventos crea una cola temporal (o se crea

una automáticamente, según el broker de mensajes) y envía
un mensaje a la cola de solicitud, pasando el nombre de la
cola temporal en el encabezado reply-to (o algún otro
atributo personalizado acordado en el encabezado del
mensaje).

2. El productor de eventos realiza una espera bloqueante en la
cola de respuesta temporal. No se necesita un selector de
mensajes porque cualquier mensaje enviado a esta cola
pertenece únicamente al productor de eventos que envió el
mensaje original.

3. El consumidor de eventos recibe el mensaje, procesa la
solicitud y envía un mensaje de respuesta a la cola de
respuesta nombrada en el encabezado reply-to.

4. El procesador de eventos recibe el mensaje y elimina la cola

temporal.

458Esta  ilustración  detalla  el  procesamiento  de  mensajes  de  solicitud-respuesta

mediante  el  uso  de  una  cola  temporal  entre  un  productor  y  un  consumidor  de

eventos.  En  el  primer  paso,  el  productor  de  eventos  envía  un  mensaje  con  el

identificador  ciento  veinticuatro  a  la  cola  de  solicitudes,  incluyendo  en  el

encabezado la instrucción de responder a la cola temporal Q novecientos noventa

y  ocho.  Acto  seguido,  en  el  segundo  paso,  el  productor  entra  en  un  estado  de

espera  mientras  monitorea  dicha  cola.  Por  su  parte,  el  consumidor  de  eventos

recibe  la  solicitud  original  y,  en  el  tercer  paso,  genera  una  respuesta  con  el

identificador ochocientos cincuenta y siete que envía de vuelta a través de la cola

de  respuesta  temporal.  Finalmente,  en  el  cuarto  paso,  el  productor  de  eventos

recibe  el  mensaje  procesado,  el  cual  contiene  un  identificador  de  correlación

vinculado a la solicitud inicial, permitiendo así completar el ciclo de comunicación

asíncrona de manera organizada. (Accesibilidad de la imagen)

Figura 15-24. Procesamiento de mensajes de solicitud-respuesta usando una cola
temporal

Aunque la técnica de la cola temporal es mucho más simple, el
broker de mensajes debe crear una cola temporal para cada solicitud
y luego eliminarla de inmediato. Esto puede ralentizar
significativamente al broker y puede afectar el rendimiento general y
la capacidad de respuesta, particularmente para grandes volúmenes
de mensajes y alta concurrencia. Por esta razón, usualmente
recomendamos usar la técnica del ID de correlación.

459Arquitectura orientada a eventos mediada

Hasta ahora en este capítulo nos hemos centrado en la EDA
coreografiada, donde los procesadores de eventos activan eventos a
través de capacidades de difusión (broadcast), y múltiples
procesadores de eventos responden al evento. Sin embargo, puede
haber ocasiones en las que un arquitecto desee más control sobre el
procesamiento de un evento. En este caso, el arquitecto puede usar
una forma orquestada de EDA conocida como topología de
mediador.

La mediator topology (topología de mediador) aborda algunas de las
deficiencias de la topología EDA coreografiada estándar que hemos
descrito hasta ahora en este capítulo. Se centra en un event
mediator (mediador de eventos), que gestiona y controla el flujo de
trabajo para iniciar eventos que requieren coordinación entre
múltiples procesadores de eventos. Los componentes de arquitectura
que conforman la topología de mediador son: un evento iniciador,
una cola de eventos, un mediador de eventos, canales de eventos y
procesadores de eventos.

Es importante destacar que la topología mediada suele utilizar
mensajes en lugar de eventos (consulta “Eventos frente a
mensajes”). Generalmente son comandos (como ship_order) en
lugar de eventos que han ocurrido (como order_shipped).

Al igual que en la topología coreografiada, el evento iniciador es lo
que comienza todo el proceso. Sin embargo, en la topología de
mediador (Figura 15-25), un mediador de eventos acepta el evento
iniciador. Solo conoce los pasos involucrados en el procesamiento del
evento, por lo que genera los mensajes derivados correspondientes
y los envía a canales de mensajes dedicados (generalmente colas)
de manera punto a punto. Los procesadores de eventos luego
escuchan los canales de eventos dedicados, procesan los mensajes y
(usualmente) responden al mediador cuando han completado su
trabajo. Los procesadores de eventos dentro de la topología de

460mediador no anuncian lo que han hecho al resto del sistema a través
de mensajes derivados adicionales.

En la mayoría de las implementaciones de la topología de mediador,
existen múltiples mediadores, cada uno usualmente asociado con un
dominio particular o una agrupación de eventos. Esto evita tener un
único punto de falla, lo cual puede ser un problema con esta
topología, y aumenta el rendimiento y la capacidad de
procesamiento general. Por ejemplo, un mediador de clientes podría
manejar todos los eventos relacionados con los clientes (como
nuevos registros de clientes y actualizaciones de perfil), mientras
que un mediador de pedidos maneja las actividades relacionadas
con los pedidos (como agregar un artículo a un carrito de compras y
finalizar la compra).

La forma en que los arquitectos eligen implementar el mediador de
eventos suele depender de la naturaleza y complejidad de los
mensajes que el mediador de eventos está procesando. Por ejemplo,
para eventos que requieren una orquestación y manejo de errores
simples, mediadores como Apache Camel, Mule ESB o Spring
Integration suelen ser suficientes. Los flujos y rutas de mensajes
dentro de este tipo de mediadores se escriben típicamente a medida
en código de programación (como Java o C#) para controlar el flujo
de trabajo del procesamiento de eventos.

Sin embargo, si el flujo de trabajo del evento requiere mucho
procesamiento condicional y múltiples rutas dinámicas con directivas
complejas de manejo de errores, entonces un mediador como
Apache ODE o el Oracle BPEL Process Manager sería una opción más
apropiada. Estos mediadores se basan en el Business Process
Execution Language (BPEL), una estructura similar a XML que
describe los pasos involucrados en el procesamiento de un evento.
Los artefactos BPEL también contienen elementos estructurados
utilizados para el manejo de errores, redirección, multidifusión, etc.
BPEL es un lenguaje potente pero relativamente complejo de

461aprender, por lo que los arquitectos suelen crear mediadores
utilizando las herramientas GUI de la suite del motor BPEL.

Esta  imagen  ilustra  la  topología  de  un  mediador  dentro  de  una  arquitectura

orientada  a  eventos,  detallando  un  flujo  de  trabajo  orquestado.  El  proceso

comienza  con  un  evento  inicial  que  se  dirige  a  una  cola  de  eventos  para  ser

recibido  por  un  mediador  de  eventos  central,  el  cual  actúa  como  el  núcleo  de

coordinación  del  sistema.  Este  mediador  distribuye  las  tareas  de  manera  dirigida

hacia  múltiples  canales  de  eventos,  los  cuales  sirven  como  vías  de  comunicación

hacia distintos procesadores de eventos. Finalmente, cada procesador, compuesto

por  diversos  componentes  internos,  se  encarga  de  ejecutar  las  acciones

específicas correspondientes a la lógica de negocio requerida. (Accesibilidad de la

imagen)

Figura 15-25. Topología de mediador

BPEL es bueno para flujos de trabajo complejos y dinámicos, pero
no funciona bien para flujos de trabajo de eventos con transacciones
de larga duración que involucran intervención humana a lo largo del
proceso del evento. Por ejemplo, supongamos que se está realizando
una operación a través de un evento iniciador place_trade. El
mediador de eventos acepta este evento, pero durante el

462procesamiento, descubre que se requiere una aprobación manual
porque la operación supera un cierto número de acciones. El
mediador de eventos ahora tiene que detener el procesamiento del
evento, notificar a un operador sénior para obtener la aprobación
manual y esperar esa aprobación. En estos casos, un motor de
Business Process Management (BPM - Gestión de Procesos de
Negocio), como jBPM, sería más apropiado que usar un mediador de
eventos.

Antes de elegir qué tipo de mediador de eventos implementar, es
importante conocer los tipos de eventos que procesará. Para eventos
complejos y de larga duración que involucran interacción humana,
Apache Camel sería extremadamente difícil de usar y mantener. Por
la misma razón, usar un motor BPM para flujos de eventos simples
desperdiciaría meses de esfuerzo en algo que Apache Camel podría
lograr en cuestión de días.

Por supuesto, es raro que todos los eventos encajen perfectamente
en una sola clase de complejidad. Recomendamos clasificar los
eventos como simples, difíciles o complejos, y enviar cada evento a
través de un mediador simple, como Apache Camel o Mule. El
mediador simple puede manejar el evento por sí mismo o reenviarlo
a otro mediador de eventos más complejo basándose en esa
clasificación de complejidad. Este modelo de delegación de
mediadores, ilustrado en la Figura 15-26, asegura que todos los
tipos de eventos sean manejados por el tipo de mediador que los
procesará de manera más efectiva.

463Este  diagrama  describe  un  modelo  de  delegación  dentro  de  una  arquitectura

orientada  a  eventos,  donde  un  evento  inicial  se  envía  a  través  de  una  cola  de

eventos  hacia  un  mediador  de  eventos  simple  basado  en  código  fuente.  Este

mediador  principal  evalúa  la  tarea  y  puede  dirigir  un  evento  de  procesamiento

directamente  a  un  procesador  de  eventos  mediante  un  canal  de  eventos,  o  bien

delegar el evento inicial por medio de colas hacia mediadores especializados. Estos

incluyen  un  mediador  de  eventos  difícil,  que  utiliza  el  lenguaje  de  ejecución  de

procesos de negocio (BPEL), y un mediador de eventos complejo, que emplea la

gestión  de  procesos  de  negocio  (BPM).  Ambos  mediadores  avanzados  coordinan

flujos de trabajo más sofisticados, enviando eventos de procesamiento a través de

464distintos  canales  hacia  múltiples  procesadores  de  eventos,  los  cuales  ejecutan  la

lógica final mediante sus componentes internos. (Accesibilidad de la imagen)

Figura 15-26. Delegación del evento al tipo apropiado de mediador de eventos

Observa en la Figura 15-26 que el Simple Event Mediator genera y
envía un mensaje derivado cuando el flujo de trabajo del evento es
lo suficientemente simple como para ser manejado por completo por
el mediador simple. Sin embargo, cuando el evento iniciador se
clasifica como difícil o complejo, el Simple Event Mediator reenvía
el evento iniciador original a los mediadores correspondientes (BPEL
o BPM). El Simple Event Mediator, habiendo interceptado el evento
original, aún podría ser responsable de saber cuándo se completa
ese evento, o simplemente podría delegar todo el flujo de trabajo
(incluida la notificación al cliente) a los otros mediadores.

Para examinar cómo funciona la topología de mediador,
consideremos el mismo sistema de ingreso de pedidos minoristas
que describimos en la sección sobre la topología coreografiada, pero
esta vez usando la topología de mediador. El mediador conoce los
pasos necesarios para procesar este evento en particular. El flujo de
eventos interno del componente mediador se ilustra en la Figura 15-
27.

465Esta imagen presenta un diagrama de flujo que detalla los pasos de un mediador

para gestionar un pedido a través de cinco etapas secuenciales. El proceso inicia

con el Paso 1: Realizar el pedido, que consiste en crear el pedido. A continuación,

el  Paso  2:  Procesar  el  pedido  incluye  enviar  un  correo  electrónico  al  cliente

informando que se ha realizado el pedido, aplicar el pago y disminuir el inventario.

El  Paso  3:  Surtir  el  pedido  abarca  seleccionar  y  empacar  el  pedido,  además  de

pedir más existencias al proveedor si es necesario. En el Paso 4: Enviar el pedido,

se envía un correo al cliente indicando que el pedido está listo para el envío y se

procede  a  enviar  el  pedido  al  cliente.  Finalmente,  el  Paso  5:  Notificar  al  cliente

consiste  en  enviar  un  correo  electrónico  informando  que  el  pedido  ha  sido

466enviado. Una nota aclaratoria resalta que los eventos dentro de los pasos dos, tres

y cuatro se realizan todos de forma concurrente. (Accesibilidad de la imagen)

Figura 15-27. Pasos del mediador para realizar un pedido

Siguiendo con el ejemplo anterior, el mismo evento iniciador (place
order) se envía al mediador de eventos a través de una cola
dedicada para su procesamiento. El mediador Customer recoge este
evento iniciador y comienza a generar mensajes derivados,
basándose en el flujo de la Figura 15-27. Los eventos mostrados en
los pasos 2, 3 y 4 se realizan de forma concurrente y serial entre
pasos. En otras palabras, el paso 3 (cumplimentar pedido) debe
completarse y confirmarse antes de que se pueda notificar al cliente
que el pedido está listo para ser enviado en el paso 4 (enviar
pedido).
Una vez que recibe el evento iniciador, el mediador Customer genera
un mensaje derivado create order, el cual envía a la cola order
placement (ver Figura 15-28). El procesador de eventos Order
Placement acepta el mensaje, valida y crea el pedido, y envía al
mediador un acuse de recibo y el ID del pedido de vuelta. En este
punto, el mediador podría enviar ese ID de pedido al cliente,
indicando que se realizó el pedido, o podría tener que continuar
hasta que todos los pasos se completen (esto dependería de las
reglas de negocio específicas sobre la realización de pedidos).

467Esta  ilustración  detalla  el  funcionamiento  de  un  mediador  de  eventos  dentro  de

una  arquitectura  dirigida  por  eventos,  utilizando  como  ejemplo  la  compra  de  un

libro como evento iniciador. El proceso se gestiona a través de un mediador central

que organiza el flujo en cinco pasos principales: el paso uno inicia la creación del

pedido; el paso dos se encarga de notificar al cliente, procesar el pago y ajustar el

468inventario;  el  paso  tres  coordina  el  cumplimiento  del  pedido  y  la  reposición  de

existencias; el paso cuatro gestiona la notificación de cumplimiento y el despacho;

y el paso cinco finaliza con el aviso de envío al cliente. A la derecha, se visualizan

los  distintos  procesadores  de  eventos,  tales  como  colocación  de  pedidos,

notificación,  pago,  inventario,  cumplimiento  de  pedidos,  almacén  y  envío,  cada

uno integrado por diversos componentes y conectados secuencialmente mediante

canales  de  comunicación  para  asegurar  que  cada  etapa  de  la  transacción  se

ejecute de manera coordinada. (Accesibilidad de la imagen)

Figura 15-28. Paso 1 del ejemplo del mediador

Ahora que el paso 1 está completo, el mediador pasa al paso 2 (ver
Figura 15-29) y genera tres mensajes derivados al mismo tiempo:
email customer, apply payment y adjust inventory. Envía los tres
a sus respectivas colas. Los tres procesadores de eventos reciben
estos mensajes, realizan sus respectivas tareas y notifican al
mediador que su procesamiento ha finalizado. El mediador debe
esperar hasta recibir la confirmación de los tres procesos paralelos
antes de pasar al paso 3. Si ocurre un error en uno de los
procesadores de eventos paralelos, el mediador puede tomar
medidas correctivas (más sobre esto más adelante en esta sección).

469Este  diagrama  ilustra  el  flujo  de  trabajo  de  un  mediador  de  eventos  durante  la

compra de un libro, la cual actúa como el evento inicial que activa el sistema. El

proceso  comienza  cuando  envías  una  instrucción  para  realizar  el  pedido  hacia  el

mediador  de  eventos,  el  cual  organiza  la  ejecución  lógica  en  cinco  pasos

numerados.  En  el  primer  paso  se  crea  el  pedido,  conectándose  con  los

470componentes del procesador de realización del pedido; el segundo paso gestiona

de forma paralela el envío de un correo al cliente para confirmar que el pedido fue

realizado, la aplicación del pago y el ajuste del inventario. Durante el tercer paso,

el  mediador  coordina  el  cumplimiento  del  pedido  y  la  reposición  de  existencias

mediante  los  servicios  de  cumplimiento  y  almacén;  seguidamente,  en  el  cuarto

paso, se envía un correo al cliente notificando que el pedido se ha completado y

se  procede  con  el  envío  físico.  Finalmente,  el  quinto  paso  concluye  el  flujo

enviando  un  último  correo  al  cliente  para  informarle  que  su  pedido  ha  sido

enviado.  A  la  derecha  de  la  imagen,  se  detallan  los  diversos  procesadores  de

eventos,  como  notificación,  pago,  inventario  y  envío,  cada  uno  compuesto  por

componentes  internos  que  ejecutan  las  tareas  específicas  asignadas  por  el

mediador  a  través  de  canales  de  mensajería  dedicados.  (Accesibilidad  de  la

imagen)

Figura 15-29. Paso 2 del ejemplo del mediador

Una vez que el mediador recibe una confirmación exitosa de todos
los procesadores de eventos en el paso 2, puede pasar al paso 3
para cumplimentar el pedido (ver Figura 15-30). Una vez más,
ambos mensajes (fulfill order y order stock) pueden ocurrir
simultáneamente. Los procesadores de eventos Order Fulfillment
y Warehouse aceptan los mensajes, realizan su trabajo y devuelven
un acuse de recibo al mediador.

471Este  diagrama  ilustra  cómo  funciona  un  mediador  de  eventos  cuando  realizas  la

compra  de  un  libro,  actuando  como  el  evento  iniciador.  El  proceso  arranca  al

colocar  el  pedido  en  una  cola  que  llega  al  mediador,  el  cual  coordina  el  flujo

mediante  cinco  pasos  lógicos.  En  el  paso  uno,  el  mediador  crea  el  pedido

vinculándose con el servicio de colocación de pedidos. En el paso dos, se envía un

472correo  al  cliente  informando  que  el  pedido  fue  realizado,  se  aplica  el  pago  y  se

ajusta  el  inventario  a  través  de  sus  respectivos  procesadores.  El  paso  tres  se

encarga  de  completar  el  pedido  y  reponer  existencias,  enviando  comandos

específicos  a  los  servicios  de  cumplimiento  y  de  almacén.  En  el  paso  cuatro,  le

informas  al  cliente  que  el  pedido  se  completó  y  se  procede  con  el  envío;

finalmente,  el  paso  cinco  consiste  en  notificar  al  cliente  que  el  producto  ha  sido

enviado. A la derecha de la imagen, puedes observar los distintos procesadores de

eventos  como  notificación,  pago,  inventario  y  envío,  los  cuales  están  integrados

por  diversos  componentes  internos  encargados  de  ejecutar  cada  tarea  dentro  de

la arquitectura. (Accesibilidad de la imagen)

Figura 15-30. Paso 3 del ejemplo del mediador

El mediador pasa al paso 4 (ver Figura 15-31) para enviar el pedido.
Este paso genera dos mensajes derivados: un mensaje ship order y
otro mensaje email customer con información específica sobre qué
hacer (notificar al cliente que el pedido está listo para ser enviado).

473Este diagrama detalla el flujo de trabajo de un mediador de eventos al comprar un

libro,  lo  cual  constituye  el  evento  inicial  para  realizar  un  pedido.  Verás  que  el

proceso se organiza en cinco etapas: en el paso uno, creas el pedido; en el paso

dos, envías un correo electrónico al cliente por el pedido realizado, aplicas el pago

y ajustas el inventario; en el paso tres, gestionas el cumplimiento del pedido y la

474reposición de existencias; en el paso cuatro, notificas al cliente que el pedido está

completado  y  ordenas  el  envío;  y  en  el  paso  cinco,  envías  un  correo  informando

que el producto ha sido despachado. En la parte derecha, se muestran los diversos

procesadores  de  eventos,  cada  uno  integrado  por  distintos  componentes,  que  se

encargan de la realización del pedido, las notificaciones, los pagos, el inventario, el

cumplimiento  del  pedido,  el  almacén  y  los  envíos,  todos  ellos  interconectados

mediante  canales  de  mensajería  para  coordinar  acciones  específicas  como  el

contacto con el cliente y la logística de entrega. (Accesibilidad de la imagen)

Figura 15-31. Paso 4 del ejemplo del mediador

Finalmente, el mediador pasa al paso 5 (ver Figura 15-32) y genera
otro mensaje contextual email customer para notificar al cliente que
el pedido ha sido enviado. Esto finaliza el flujo de trabajo. El
mediador marca el flujo del evento iniciador como completo y
elimina todo el estado asociado con dicho evento.

475Esta imagen ilustra el flujo de trabajo en una topología de mediador dentro de una

arquitectura orientada a eventos, comenzando con la compra de un libro como el

evento  inicial  que  dispara  la  acción  de  realizar  un  pedido.  El  proceso  central  es

gestionado por un mediador de eventos que organiza la ejecución en cinco etapas:

el  primer  paso  consiste  en  crear  el  pedido,  enviando  la  instrucción  al  servicio  de

476colocación de pedidos; el segundo paso incluye notificar al cliente, aplicar el pago

y  ajustar  el  inventario,  interactuando  con  los  servicios  de  notificación,  pago  e

inventario.  En  el  tercer  paso  se  procede  a  completar  el  pedido  y  reponer

existencias  a  través  de  los  servicios  de  cumplimiento  y  almacén,  mientras  que  el

cuarto  paso  implica  enviar  una  nueva  notificación  al  cliente  y  despachar  el

producto  mediante  el  servicio  de  envío.  Finalmente,  el  quinto  paso  cierra  el  ciclo

notificando  al  cliente  que  su  pedido  ha  sido  enviado,  demostrando  cómo  el

mediador  coordina  mensajes  dirigidos  a  componentes  específicos  para  asegurar

que  cada  tarea  se  realice  de  manera  lógica  y  eficiente.  (Accesibilidad  de  la

imagen)

Figura 15-32. Paso 5 del ejemplo del mediador

En esta topología, a diferencia de la topología coreografiada, el
componente mediador tiene conocimiento y control sobre el flujo de
trabajo. Puede mantener el estado del evento y gestionar el manejo
de errores, la capacidad de recuperación y el reinicio. Por ejemplo,
supón en nuestro ejemplo que el pago no se aplicó porque la tarjeta
de crédito ha caducado. Cuando el mediador recibe esta condición
de error, sabe que el pedido no puede cumplimentarse (paso 3)
hasta que se aplique el pago, por lo que detiene el flujo de trabajo y
registra el estado de la solicitud en su propio almacenamiento de
datos persistente. Una vez que el pago finalmente se aplica, el flujo
de trabajo puede reiniciarse desde donde se quedó (en este caso, al
comienzo del paso 3).

Si bien la topología de mediador aborda los problemas asociados con
la topología coreografiada, tiene sus propias desventajas. En primer
lugar, es muy difícil modelar de forma declarativa el procesamiento
dinámico que ocurre dentro de un flujo de eventos complejo. Como
resultado, muchos flujos de trabajo dentro de la topología de
mediador solo manejan el procesamiento general, pero utilizan un
modelo híbrido que combina las topologías de mediador y
coreografiada para abordar la naturaleza dinámica del procesamiento
de eventos complejos, como condiciones de falta de stock u otros

477errores no típicos. Además, aunque los procesadores de eventos
pueden escalar fácilmente de la misma manera que en la topología
coreografiada, el mediador también debe escalar, algo que
ocasionalmente produce un cuello de botella en el flujo general de
procesamiento de eventos. Los procesadores de eventos no están
tan altamente desacoplados en la topología de mediador como lo
están en la topología coreografiada. Finalmente, el rendimiento no
es tan bueno en esta topología, porque el mediador controla el
procesamiento de eventos.

El equilibrio entre las topologías coreografiada y de mediador se
reduce esencialmente a sopesar el control del flujo de trabajo y la
capacidad de manejo de errores frente al alto rendimiento y la
escalabilidad. Aunque el rendimiento y la escalabilidad siguen siendo
buenos dentro de la topología de mediador, no son tan altos como
con la topología coreografiada.

Topologías de datos

Con toda esta charla sobre eventos y procesamiento de eventos, es
fácil olvidarse del lado de los datos de la EDA. Las topologías de
bases de datos son un aspecto único e interesante de este estilo
arquitectónico. Ofrece muchas opciones, cada una con
compensaciones significativas que pueden tener un gran impacto en
la arquitectura general. Para describir las diferentes topologías de
bases de datos dentro de la EDA, utilizaremos una versión
simplificada del ejemplo que mostramos en la Figura 15-3 (ver
Figura 15-33).
Cuando un cliente realiza un pedido, el procesador de eventos Order
Placement crea el pedido y luego activa un evento order placed, al
cual responden tanto los procesadores de eventos Payment como
Inventory. Una vez aplicado el pago, el procesador de eventos
Order Fulfillment ayuda al empaquetador de pedidos a preparar el
pedido y luego activa un evento order fulfilled. El procesador de

478eventos Shipping responde al evento order fulfilled enviando el
pedido al cliente, completando el procesamiento y cumpliendo la
solicitud del cliente.

Esta imagen ilustra el flujo de trabajo de un sistema para realizar un pedido de un

libro,  donde  los  rectángulos  azules  representan  servicios  y  los  blancos  indican

eventos. Todo comienza con el servicio de colocación de pedidos, el cual genera el

evento de pedido realizado; a partir de aquí, el flujo se divide hacia el servicio de

inventario, que culmina en un inventario actualizado, y hacia el servicio de pagos.

Una vez que se registra el pago aplicado, se activa el servicio de cumplimiento de

pedidos,  el  cual  dispara  el  evento  de  pedido  cumplido  para  que  el  servicio  de

envíos entre en acción y finalice el proceso con la notificación de pedido enviado.

(Accesibilidad de la imagen)

Figura 15-33. Un ejemplo simplificado del sistema de ingreso de pedidos de
ejemplo usando EDA

479Una complicación de la EDA es que el procesador de eventos Order
Placement necesita conocer dos piezas de información: cuántos
artículos hay actualmente en stock y qué opciones de envío están
disponibles según la ubicación del cliente. Cómo obtiene esta
información dependerá del tipo de topología de base de datos que
utilice la arquitectura. Veamos cada opción de topología de base de
datos para ver sus compensaciones significativas.

Topología de base de datos monolítica

La primera, y quizás la más común, topología de base de datos
utilizada dentro de la EDA es la topología de base de datos
monolítica única. Con esta topología, todos los datos están
disponibles para todos los procesadores de eventos a través de una
base de datos central.

El principal beneficio de la topología de base de datos monolítica es
que cualquier procesador de eventos puede consultar los datos que
necesita directamente de la base de datos, sin tener que
comunicarse de forma síncrona con ningún otro procesador de
eventos. Esta es una ventaja significativa, ya que las arquitecturas
orientadas a eventos se basan en procesadores de eventos
altamente desacoplados que se comunican a través de
comunicaciones asíncronas. En la Figura 15-34, el procesador de
eventos Order Placement simplemente puede consultar la base de
datos monolítica central para recuperar la cantidad de artículos
actualmente en stock y las opciones de envío del cliente.

480Esta  imagen  ilustra  la  topología  de  una  base  de  datos  monolítica  dentro  de  un

sistema de arquitectura dirigida por eventos, tomando como ejemplo el proceso de

realizar un pedido de un libro, basado en la obra Fundamentos de la arquitectura

de software. El flujo comienza cuando el servicio de colocación de pedidos recibe

la  instrucción  de  compra  e  interactúa  con  una  base  de  datos  central,  de  donde

provienen las consultas de inventario y envío. Una vez que el pedido es realizado,

el  evento  activa  simultáneamente  el  servicio  de  inventario,  que  notifica  el

inventario  actualizado,  y  el  servicio  de  pago.  Tras  confirmar  que  el  pago  ha  sido

aplicado, se inicia el servicio de cumplimiento de pedidos, el cual marca el pedido

como  cumplido  y  activa  el  servicio  de  envío.  Finalmente,  este  último  proceso

concluye cuando el pedido es enviado, mientras todos los servicios mantienen una

481conexión  directa  con  la  base  de  datos  única  para  leer  y  escribir  información

durante cada etapa del flujo de trabajo. (Accesibilidad de la imagen)

Figura 15-34. Con la topología de base de datos monolítica, los datos están
disponibles directamente desde la base de datos

Si bien la topología de base de datos monolítica admite el
desacoplamiento y limita la comunicación entre los procesadores de
eventos, conlleva algunas desventajas complicadas, la primera de las
cuales es la tolerancia a fallos. Si la base de datos monolítica central
falla o se cae por mantenimiento, todos los procesadores de eventos
dejan de estar disponibles.

El segundo problema es la escalabilidad. Debido a que las
arquitecturas orientadas a eventos utilizan comunicación asíncrona,
cada procesador de eventos puede escalar independientemente de
los demás. El canal de eventos actúa esencialmente como un punto
de contrapresión para que los procesadores de eventos individuales
puedan escalar según sea necesario, independientemente de si otros
procesadores de eventos también escalan. Sin embargo, si todos los
procesadores de eventos están consultando y escribiendo
simultáneamente en la misma base de datos, la base de datos debe
escalar para satisfacer estas demandas. Muchas bases de datos son
incapaces de lograr esto con cargas de concurrencia elevadas.

El tercer problema es el control de cambios. Cuando cambia la
estructura de la base de datos (como al eliminar una columna o un
atributo), múltiples procesadores de eventos se ven afectados y
deben coordinarse, incluso para un solo cambio en la base de datos.

Finalmente, la topología de base de datos monolítica crea
necesariamente un único cuanto arquitectónico, debido a la base de
datos monolítica compartida.

482Topología de base de datos de dominio

Otra posible topología de base de datos dentro de la EDA es la
topología de base de datos de dominio, la cual agrupa los
procesadores de eventos en varios dominios, cada uno de los cuales
posee su propia base de datos (Figura 15-35).

483Esta  imagen  ilustra  un  flujo  de  arquitectura  basada  en  eventos  que  comienza

cuando  decides  realizar  un  pedido  de  un  libro.  El  proceso  inicia  en  el  servicio  de

realización de pedidos, el cual genera el evento de pedido realizado y se conecta a

una base de datos central. A partir de ahí, la información fluye hacia el servicio de

inventario, que marca el inventario como actualizado, y simultáneamente hacia el

servicio  de  pagos,  que  confirma  que  el  pago  ha  sido  aplicado;  ambos  servicios

también  interactúan  con  la  base  de  datos.  Una  vez  procesado  el  pago,  el  flujo

continúa hacia el servicio de cumplimiento de pedidos, que emite la notificación de

pedido  cumplido  y  se  vincula  a  otra  base  de  datos.  Finalmente,  el  servicio  de

envíos toma el relevo para generar el evento de pedido enviado, completando así

todo el ciclo de la transacción. (Accesibilidad de la imagen)

Figura 15-35. La topología de base de datos de dominio utiliza una base de datos
independiente para cada dominio

484Las principales ventajas de la topología de base de datos de dominio
sobre la topología de base de datos monolítica, que se derivan de
estar particionada por dominios, son una mejor tolerancia a fallos,
escalabilidad y control de cambios. En el ejemplo mostrado en la
Figura 15-35, si la base de datos del dominio de procesamiento de
pedidos (la asociada con los procesadores de eventos Order
Fulfillment y Order Shipping) falla o no está disponible debido al
mantenimiento, el dominio de realización de pedidos sigue estando
plenamente operativo y puede seguir aceptando pedidos. El canal de
eventos que contiene el evento derivado payment applied actúa
como un punto de contrapresión, encolando eventos hasta que la
base de datos de procesamiento de pedidos esté disponible. Lo
mismo ocurre con la escalabilidad y el control de cambios; cada base
de datos de dominio solo tiene que preocuparse por escalar en
función de los procesadores de eventos específicos de su dominio, y
solo esos procesadores de eventos con alcance de dominio deben
cambiar si la estructura de la base de datos cambia.

Sin embargo, considera las dos piezas de información que necesita el
procesador de eventos Order Placement: la cantidad de libros
actualmente disponibles y las opciones de envío. Con la topología de
base de datos de dominio, el procesador de eventos Order
Placement simplemente puede consultar su base de datos de
dominio para obtener el inventario de libros, de forma similar a
cómo recuperaba esta información con la topología de base de datos
monolítica. No obstante, debe realizar una llamada síncrona al
procesador de eventos Order Shipping para recuperar las opciones
de envío, acoplando así síncronamente estos servicios (ver Figura
15-36).

485Este  diagrama  ilustra  la  topología  de  base  de  datos  por  dominio  dentro  de  una

arquitectura orientada a eventos, tomando como ejemplo el proceso para realizar

un pedido de un libro. El flujo comienza en el servicio de realización de pedidos, el

cual  debe  obtener  información  de  dos  fuentes  distintas:  realiza  una  consulta  de

inventario  que  proviene  de  la  base  de  datos  local  y,  simultáneamente,  requiere

que  los  datos  de  envío  provengan  del  servicio  de  envío  a  través  de  una  llamada

síncrona, lo que genera un acoplamiento temporal entre ambos. A medida que el

proceso  avanza  de  forma  asíncrona,  se  disparan  eventos  como  pedido  realizado,

pago aplicado y pedido cumplido, los cuales activan respectivamente al servicio de

pago,  al  servicio  de  inventario  —que  genera  un  inventario  actualizado—  y  al

servicio de cumplimiento de pedidos. El ciclo concluye cuando el servicio de envío

procesa la información y emite el evento de pedido enviado. Estructuralmente, el

gráfico  muestra  una  segmentación  de  datos  donde  los  servicios  de  inventario  y

pago  comparten  una  base  de  datos  de  dominio,  mientras  que  los  servicios  de

cumplimiento  y  envío  utilizan  otra  distinta,  evidenciando  cómo  la  necesidad  de

486datos  externos  puede

forzar

interacciones

síncronas  en  un  entorno

mayoritariamente asíncrono. (Accesibilidad de la imagen)

Figura 15-36. Los datos necesarios para el procesador de eventos Order Placement
pueden requerir comunicación síncrona con un procesador de eventos en otro
dominio

Los arquitectos deben tratar de evitar el acoplamiento síncrono en
una arquitectura altamente dinámica y desacoplada como la EDA.
Las llamadas síncronas pueden afectar la tolerancia a fallos y la
escalabilidad, anulando muchos de los beneficios de utilizar esta
topología. Verifica siempre que los dominios permanezcan bastante
independientes entre sí y minimiza las llamadas síncronas entre
servicios tanto como sea posible. Si se requiere demasiada
comunicación síncrona entre los procesadores de eventos, reevalúa
los límites del dominio, combina los dominios en uno solo o cámbiate
a una topología de base de datos monolítica.

Topología de datos dedicada

Otra opción viable dentro de la EDA es la topología de base de datos
dedicada, comúnmente conocida en el mundo de los microservicios
como el patrón de base de datos por servicio. Con esta topología de
base de datos, cada procesador de eventos posee su propia base de
datos dedicada en un contexto delimitado bien definido, de forma
similar a los microservicios (ver “Topologías de datos” en el Capítulo
18). Esta topología se ilustra en la Figura 15-37.

487Esta  imagen  ilustra  un  flujo  de  trabajo  dentro  de  una  arquitectura  orientada  a

eventos para el proceso de realizar un pedido de un libro. El ciclo comienza con la

acción  de  haz  un  pedido  de  un  libro,  la  cual  es  procesada  por  el  servicio  de

colocación de pedidos que guarda la información en su base de datos y activa el

evento  de  pedido  realizado.  Este  evento  dispara  en  paralelo  el  servicio  de

inventario, que actualiza su propia base de datos y genera el evento de inventario

actualizado,  y  el  servicio  de  pagos,  que  tras  registrar  los  datos  en  su  base  de

datos, emite el evento de pago aplicado. Posteriormente, el pago aplicado activa el

servicio  de  cumplimiento  de  pedidos,  el  cual  interactúa  con  su  base  de  datos  y

genera el evento de pedido cumplido. Finalmente, este evento activa el servicio de

envío, que registra la operación en su base de datos y concluye el proceso con el

evento de pedido enviado. (Accesibilidad de la imagen)

Figura 15-37. La topología de base de datos dedicada de EDA utiliza una base de
datos independiente para cada procesador de eventos

488No es de extrañar que la topología de base de datos dedicada tenga
los niveles más altos de tolerancia a fallos, escalabilidad y control de
cambios de todas las topologías disponibles. Si un procesador de
eventos o una base de datos falla, la interrupción se aísla
únicamente a ese procesador de eventos; todos los demás
procesadores de eventos funcionan con normalidad. Las bases de
datos solo necesitan escalar en función del único procesador de
eventos dentro de su contexto delimitado, lo que convierte a esta
topología en la más escalable de las tres analizadas en esta sección.
Finalmente, los cambios en la estructura de la base de datos solo
afectan al procesador de eventos vinculado a esa base de datos.

En el lado negativo, dependiendo de la pila de tecnología de la base
de datos, esta puede ser una opción muy costosa. Quizás la mayor
desventaja, sin embargo, sea el acoplamiento dinámico síncrono
entre los procesadores de eventos. Para ilustrar esta desventaja,
observa de nuevo las dos piezas de información que el procesador
de eventos Order Placement necesita para su procesamiento: el
inventario de libros y las opciones de envío. En esta topología, el
procesador de eventos Order Placement tendría que realizar
llamadas síncronas tanto al procesador de eventos Inventory como
al procesador de eventos Order Shipment para obtener la
información que necesita, formando puntos de acoplamiento
síncrono estrictos en toda la arquitectura (como se muestra en la
Figura 15-38). Al igual que con la topología de base de datos de
dominio, identifica todos los requisitos relacionados con los datos en
cada procesador de eventos antes de seleccionar esta opción de
topología de base de datos.

489Esta  ilustración  muestra  un  diagrama  de  flujo  de  un  sistema  de  arquitectura  de

software para realizar un pedido de un libro. El proceso comienza en el servicio de

realización de pedidos, el cual está conectado a su propia base de datos y realiza

llamadas  síncronas  hacia  los  servicios  de  inventario  y  envío  para  obtener  datos

específicos;  en  el  diagrama  se  indica  que  los  datos  de  inventario  provienen  del

servicio de inventario y los datos de envío provienen del servicio de envío a través

de  dichas  llamadas  síncronas.  A  lo  largo  del  flujo,  se  presentan  diversos

componentes interconectados por eventos asíncronos representados como pedido

realizado,  pago  aplicado,  pedido  cumplido  y  pedido  enviado.  Cada  etapa  cuenta

con  su  propio  microservicio  especializado,  incluyendo  el  servicio  de  inventario,  el

servicio  de  pago,  el  servicio  de  cumplimiento  de  pedidos  y  el  servicio  de  envío,

490cada  uno  vinculado  a  una  base  de  datos  independiente  para  procesar

actualizaciones como el inventario actualizado. (Accesibilidad de la imagen)

Figura 15-38. Los datos necesarios para el procesador de eventos Order
Placement pueden requerir comunicación síncrona con otros procesadores de
eventos

La topología de base de datos dedicada es una buena opción cuando
los procesadores de eventos son mayoritariamente autónomos,
necesitando únicamente los datos dentro de su propio contexto
delimitado y base de datos correspondiente. Si los procesadores de
eventos se comunican demasiado (ver “Gobernanza”), el arquitecto
debería considerar pasar a la topología de base de datos de dominio
o incluso a la monolítica para mejorar el rendimiento y la
escalabilidad generales. Sin embargo, si la situación específica
implica cambios estructurales frecuentes en la base de datos, eso
podría justificar un equilibrio entre estas características operativas
para minimizar la cantidad de procesadores de eventos afectados.

Consideraciones sobre la nube

Las arquitecturas orientadas a eventos funcionan bien con entornos
e implementaciones basados en la nube, principalmente debido a su
naturaleza altamente desacoplada. La EDA puede aprovechar
fácilmente los servicios asíncronos proporcionados por los
proveedores de la nube, y la naturaleza elástica de la infraestructura
y los servicios basados en la nube se adapta a su forma.
Básicamente, los entornos basados en la nube son una buena
combinación para la EDA.

Riesgos comunes

Uno de los principales riesgos asociados con la EDA es que su
procesamiento de eventos no determinista puede causar efectos
secundarios: por ejemplo, que los procesadores de eventos activen

491inesperadamente eventos derivados o que no respondan a un evento
cuando deberían. Los flujos de trabajo de eventos pueden volverse
muy complejos en una arquitectura orientada a eventos y, muchas
veces, es difícil saber exactamente qué sucederá cuando se activa
un evento.

Otro gran riesgo es tener demasiado acoplamiento estático (y, por lo
tanto, fragilidad) dentro de la arquitectura orientada a eventos.
Aunque la EDA está altamente acoplada de forma dinámica, los
contratos de carga útil de eventos (ver “Carga útil del evento”)
también pueden introducir un acoplamiento estático estrecho.
Cambiar un contrato puede ser una tarea de gran magnitud, ya que
los arquitectos no siempre saben qué procesadores de eventos
responden a un evento en particular. Cuando el contrato de carga
útil de un evento cambia, puede afectar negativamente a varios
otros procesadores de eventos, aumentando la fragilidad general de
este estilo arquitectónico. Las cargas útiles de eventos basadas en
claves ayudan a mitigar este riesgo, pero los riesgos de esta práctica
incluyen problemas con la escalabilidad y el rendimiento, además de
la posibilidad de eventos anémicos (ver “Carga útil del evento”).

Ten cuidado también con el exceso de comunicación síncrona entre
los procesadores de eventos. La arquitectura orientada a eventos
obtiene sus superpoderes de sus procesadores de eventos altamente
desacoplados de forma dinámica. Sin embargo, si los procesadores
de eventos necesitan comunicarse síncronamente con frecuencia, es
una buena señal de que la EDA no es el estilo arquitectónico más
apropiado.

Finalmente, la gestión del estado global es tanto un riesgo como un
desafío en la EDA. Es bueno saber cuándo el evento iniciador se ha
procesado por completo, pero eso puede ser muy difícil de
determinar debido al procesamiento de eventos en paralelo,
asíncrono y no determinista de la EDA. Ocasionalmente, un
arquitecto puede identificar el punto final de procesamiento y hacer
que el procesador de eventos que aceptó el evento iniciador se

492suscriba a ese evento de "finalización", pero en la mayoría de los
casos esto es difícil de determinar. Como resultado, es difícil saber
cuándo se ha procesado por completo un evento iniciador, o incluso
conocer su estado actual.

Gobernanza

La mayor parte de la gobernanza asociada con la EDA es no
estructural y requiere observabilidad en forma de registros como
parte de una malla de gobernanza global. Dependiendo de la
infraestructura y el entorno, es posible que algunas métricas de
gobernanza asociadas con la EDA deban recopilarse manualmente.

Las dos áreas principales de gobernanza en este estilo son el
acoplamiento estático a través de la gestión de contratos y el
acoplamiento dinámico a través de llamadas síncronas. Ambos
aspectos se consideran deterioro estructural en la EDA, por lo que es
importante vigilarlos.

Desde una perspectiva de acoplamiento estático, los arquitectos
pueden establecer una gobernanza en torno a aspectos como la tasa
de cambio de los contratos de carga útil de eventos y el
acoplamiento de marca (stamp coupling) general. Cambiar los
contratos puede ser muy riesgoso en la EDA debido a su naturaleza
desacoplada. Cambiar un contrato de evento, particularmente uno
sin un esquema asociado, puede romper un procesador de eventos
descendente. Este es un riesgo particular en la EDA porque es muy
difícil probar flujos de eventos de extremo a extremo que sean no
deterministas.

El acoplamiento de marca (ver “Carga útil del evento”) se puede
gobernar registrando y observando continuamente qué campos en
un contrato de evento no están siendo utilizados por los
procesadores de eventos que responden al evento. Observar estos
campos no utilizados puede ayudar a reducir el tamaño del contrato,
disminuir el ancho de banda y ayudar a gestionar el acoplamiento de

493marca y los correspondientes cambios innecesarios en los
procesadores de eventos.

Desde el punto de vista del acoplamiento dinámico, los arquitectos
pueden escribir funciones de fitness automatizadas para observar y
rastrear la comunicación síncrona entre los procesadores de eventos
a través de registros y otros medios observables (como anotaciones
en el código fuente o el uso de bibliotecas de identificadores
personalizados síncronos estándar). Cualquier comunicación síncrona
en una arquitectura orientada a eventos debe rastrearse y discutirse
para asegurar que sea necesaria, particularmente si se utiliza una
topología de base de datos de dominio o dedicada.

Consideraciones sobre la topología de equipos

La EDA se considera en gran medida una arquitectura particionada
técnicamente debido a los numerosos artefactos que componen
cada dominio: múltiples procesadores de eventos, canales de
eventos, agentes de mensajes y, posiblemente, bases de datos,
según la topología de la base de datos. No obstante, puede
funcionar bien cuando los equipos están alineados dentro de áreas
de dominio (como equipos multifuncionales con especialización).
Dicho esto, tipos específicos de topologías de equipos (ver
“Topologías de equipos y arquitectura”) podrían encontrar que la
EDA es un desafío.

Aquí tienes algunas consideraciones sobre la alineación entre estas
topologías de equipos específicas y la EDA:

Equipos alineados con el flujo (Stream-aligned teams)

Dependiendo del tamaño del sistema, los equipos alineados
con el ﬂujo podrían tener diﬁcultades para implementar
cambios basados en el dominio, debido a la naturaleza
desacoplada de los procesadores de eventos. Dado que los
dominios y subdominios en la EDA se implementan

494típicamente con múltiples procesadores de eventos y
eventos derivados, para los equipos alineados con el ﬂujo
podría ser un reto comprender todas estas piezas móviles.
Por ejemplo, añadir un paso al ﬂujo de trabajo de
realización de pedidos podría requerir cambiar múltiples
procesadores de eventos, así como reestructurar cómo (y
cuándo) se activan los eventos derivados existentes. Cuanto
más grande y compleja sea la arquitectura orientada a
eventos, menos efectivos serán los equipos alineados con el
ﬂujo.

Equipos facilitadores (Enabling teams)

Debido a la integración requerida entre los procesadores de
eventos basada en eventos derivados y sus contratos, los
equipos facilitadores no funcionan bien en las arquitecturas
orientadas a eventos. La experimentación y la eﬁciencia de
los equipos facilitadores dentro de un ﬂujo pueden alterar la
comprensión y la gestión de un equipo alineado con el ﬂujo
sobre un ﬂujo de eventos global, y por lo general requiere
demasiada coordinación entre los equipos alineados con el
ﬂujo y los equipos facilitadores.

Equipos de subsistemas complicados (Complicated-subsystem
teams)

Los equipos de subsistemas complicados funcionan bien con
la EDA debido a su naturaleza desacoplada y asíncrona. El
procesamiento complejo puede aislarse fácilmente a través
de procesadores de eventos independientes, y el equipo de
subsistemas complicados puede enfocarse en ellos, dejando
el procesamiento menos complicado a los equipos alineados
con el ﬂujo. Debido a que los procesadores de eventos están
altamente desacoplados de forma dinámica, los equipos
alineados con el ﬂujo solo necesitan coordinarse con los

495equipos de subsistemas complicados para los contratos
estáticos de carga útil de eventos y los eventos derivados.

Equipos de plataforma (Platform teams)

En la EDA, los desarrolladores pueden aprovechar los
beneﬁcios de la topología de equipos de plataforma
utilizando herramientas, servicios, APIs y tareas comunes,
debido principalmente a la partición técnica de la EDA. Esto
es especialmente cierto si los equipos tratan las partes de la
EDA relacionadas con la infraestructura (como los agentes
de mensajes, concentradores de eventos, buses de eventos y
otros artefactos de canales de eventos) como elementos
relacionados con la plataforma.

Características del estilo

Una calificación de una estrella en la tabla de calificación de
características de la Figura 15-39 significa que la característica
arquitectónica específica no está bien respaldada en la arquitectura,
mientras que una calificación de cinco estrellas significa que es una
de las características más fuertes de ese estilo. Las definiciones para
cada característica identificada en el cuadro de mando se pueden
encontrar en el Capítulo 4.

La arquitectura orientada a eventos es principalmente una
arquitectura particionada técnicamente, en el sentido de que
cualquier dominio en particular se distribuye a través de múltiples
procesadores de eventos y se une mediante agentes, contratos
(carga útil del evento) y temas. Los cambios en un dominio en
particular suelen afectar a múltiples procesadores de eventos y otros
artefactos de mensajería, por lo que la EDA generalmente no se
considera particionada por dominios.

496Esta  tabla  comparativa  evalúa  diversas  características  arquitectónicas  mediante

una calificación por estrellas, destacando un costo total de nivel intermedio. En la

sección  estructural,  se  observa  un  particionamiento  de  tipo  técnico  con  una

cantidad de cuantos que varía de uno a muchos, resaltando una modularidad alta

frente  a  una  simplicidad  limitada.  Dentro  del  área  de  ingeniería,  la  arquitectura

brilla  por  su  máxima  capacidad  de  evolutividad  y  una  sólida  mantenibilidad,

aunque  presenta  dificultades  en  su  capacidad  de  prueba  y  mantiene  un  nivel

moderado de facilidad de despliegue. Sus mayores virtudes aparecen en el plano

operativo,  donde  alcanza  la  excelencia  en  capacidad  de  respuesta  y  tolerancia  a

fallos,  acompañada  de  una  notable  escalabilidad  y  una  elasticidad  aceptable,  lo

que  sugiere  un  sistema  robusto  y  ágil  diseñado  para  adaptarse  a  demandas

variables. (Accesibilidad de la imagen)

Figura 15-39. Calificaciones de las características de la EDA

497El número de cuantos (quanta) dentro de la EDA puede variar de
uno a muchos, dependiendo de las interacciones con la base de
datos dentro de cada procesador de eventos y de si el sistema utiliza
el procesamiento de solicitud-respuesta. Aunque la comunicación en
una EDA se basa en llamadas asíncronas, si múltiples procesadores
de eventos comparten una sola instancia de base de datos, todos
estarían contenidos dentro del mismo cuanto arquitectónico. Lo
mismo ocurre con el procesamiento de solicitud-respuesta: aunque
la comunicación entre los procesadores de eventos siga siendo
asíncrona, si se necesita una respuesta inmediata del consumidor de
eventos, esto une esos procesadores de eventos de forma síncrona,
formando un solo cuanto.

Por ejemplo, imagina que un procesador de eventos envía una
solicitud a otro procesador de eventos para realizar un pedido. El
primer procesador de eventos debe esperar un ID de pedido del otro
procesador de eventos para continuar. Si el segundo procesador de
eventos (el que realiza el pedido y genera un ID de pedido) no está
disponible, el primer procesador de eventos no puede continuar. Esto
significa que forman parte del mismo cuanto de arquitectura y
comparten las mismas características arquitectónicas, a pesar de que
ambos envían y reciben mensajes asíncronos.

La arquitectura orientada a eventos tiene una calificación muy alta
(de 4 a 5 estrellas) en rendimiento, escalabilidad y tolerancia a
fallos, que son sus principales fortalezas. Su alto rendimiento se
logra combinando comunicaciones asíncronas con un procesamiento
altamente paralelo. La alta escalabilidad se consigue mediante el
equilibrado de carga programático de los procesadores de eventos
(también llamados competing consumers [consumidores
competidores] y consumer groups [grupos de consumidores]). A
medida que aumenta la carga de solicitudes, se pueden añadir
programáticamente procesadores de eventos adicionales para
manejar las solicitudes extra. La razón por la que solo le dimos
cuatro estrellas (en lugar de cinco) es por la base de datos (consulta

498el Capítulo 16, sobre arquitecturas basadas en el espacio, para ver
un ejemplo de una calificación de cinco estrellas para estas
características). La EDA logra la tolerancia a fallos a través de sus
procesadores de eventos asíncronos y desacoplados, que
proporcionan consistencia eventual y el procesamiento de flujos de
trabajo de eventos. Si otros procesadores descendentes no están
disponibles, siempre que la interfaz de usuario o un procesador de
eventos que realiza una solicitud no necesite una respuesta
inmediata, el sistema puede procesar el evento en un momento
posterior.

La EDA tiene una calificación relativamente baja en simplicidad y
capacidad de prueba generales, debido principalmente a sus flujos
de eventos dinámicos y no deterministas. En los modelos basados en
solicitudes, los flujos deterministas son relativamente fáciles de
probar porque sus rutas y resultados son generalmente conocidos.
Este no es el caso con el modelo orientado a eventos. A veces, los
arquitectos simplemente no saben cómo reaccionarán los
procesadores de eventos ante eventos dinámicos o qué mensajes
podrían producir. Estos se conocen como flujos de trabajo no
deterministas. Los "diagramas de árbol de eventos" de estos
sistemas pueden ser extremadamente complejos, generando cientos
o incluso miles de escenarios, lo que los hace muy difíciles de
gobernar y probar.

Finalmente, las EDA son altamente evolutivas, de ahí la calificación
de cinco estrellas. Añadir nuevas funciones a través de procesadores
de eventos existentes o nuevos es relativamente sencillo. Al
proporcionar ganchos (hooks) mediante eventos derivados
activados, el evento y sus datos correspondientes ya están
disponibles para otros procesamientos, por lo que no se requieren
cambios en la infraestructura ni en los procesadores de eventos
existentes para añadir esa nueva funcionalidad.

Las desventajas de la EDA incluyen la dificultad para controlar el
flujo de trabajo global asociado con un evento iniciador. El

499procesamiento de eventos es muy dinámico debido a las condiciones
cambiantes, y es difícil saber cuándo se ha completado la
transacción comercial basada en el evento iniciador.

El manejo de errores también es un gran desafío con la EDA. Debido
a que normalmente no hay un mediador que monitoree o controle la
transacción comercial (excepto con la topología de mediador), si
ocurre una falla, los otros servicios no se enterarán de la caída. El
proceso de negocio basado en ese evento iniciador se queda
atascado y es incapaz de avanzar sin algún tipo de intervención
automatizada o manual, incluso mientras todos los demás procesos
continúan sin tener en cuenta el error. Por ejemplo, si el procesador
de eventos Payment (Pago) en nuestro sistema de pedidos falla y no
completa su tarea asignada, el procesador de eventos Inventory
(Inventario) seguirá ajustando el inventario, y todos los demás
procesadores de eventos posteriores reaccionarán como si todo
estuviera bien.

Reiniciar una transacción comercial (recuperabilidad) es muy difícil
de hacer en la EDA. Debido a que se han tomado otras acciones de
forma asíncrona a través del procesamiento del evento iniciador,
muchas veces simplemente no es factible volver a enviar el evento
iniciador.

Elección entre modelos basados en solicitudes
y basados en eventos

Tanto el modelo basado en solicitudes como el basado en eventos
son enfoques viables para diseñar sistemas de software. Sin
embargo, elegir el modelo adecuado es esencial para el éxito.
Recomendamos elegir el modelo basado en solicitudes para
peticiones bien estructuradas y orientadas a datos (como recuperar
los datos del perfil de un cliente), cuando la prioridad es la certeza y
el control sobre el flujo de trabajo. Recomendamos elegir el modelo
basado en eventos para eventos flexibles y basados en acciones que

500requieran altos niveles de capacidad de respuesta y escala, con un
procesamiento de usuario complejo y dinámico.

Comprender las compensaciones (trade-offs) del modelo basado en
eventos también ayuda a determinar cuál es el más adecuado. La
Tabla 15-2 enumera las ventajas y desventajas del modelo basado
en eventos de la EDA.

Tabla 15-2. Compensaciones del modelo orientado a eventos

Ventajas sobre el basado
en solicitudes

Compensaciones (Trade-offs)

Mejor respuesta al contenido
de usuario dinámico

Solo admite consistencia eventual

Mejor escalabilidad y
elasticidad

Menos control sobre el flujo de
procesamiento

Mejor agilidad y gestión de
cambios

Menos certeza sobre el resultado
del flujo de eventos

Mejor adaptabilidad y
extensibilidad

Difícil de probar y depurar

Mejor capacidad de respuesta
y rendimiento

Mejor toma de decisiones en
tiempo real

Mejor reacción al
conocimiento de la situación

501Ejemplos y casos de uso

Cualquier problema de negocio centrado en responder a cosas que
suceden en el sistema (ya sea internas o externas) es un buen
candidato para la EDA. El ejemplo del sistema de entrada de pedidos
que hemos utilizado a lo largo de este capítulo es un buen caso de
uso para la EDA, ya que permite el procesamiento paralelo y
desacoplado de un pedido. Los sistemas que requieren altos niveles
de capacidad de respuesta, rendimiento, escalabilidad, tolerancia a
fallos y elasticidad también son excelentes candidatos para la EDA.

Otro buen caso de uso para demostrar el poder y la eficacia de la
EDA es nuestro ejemplo recurrente del sistema de subastas Going,
Going, Gone, donde los usuarios pujan por artículos puestos a
subasta hasta que una puja final no tiene competencia y el postor
gana ese artículo. En estos sistemas, el número de postores suele
ser desconocido, lo que requiere tanto escalabilidad como
elasticidad, especialmente si la subasta es programada y la puja
llega a su fin. Estos sistemas también necesitan altos niveles de
capacidad de respuesta. Sin embargo, quizás la mejor razón por la
que los sistemas de pujas en línea y la EDA encajan tan bien es que
la EDA considera que realizar una puja no es una solicitud realizada
al sistema, sino un evento que ha ocurrido.

Como muestra la Figura 15-40, se producen muchas acciones en el
sistema cuando un postor realiza una puja. Todas estas acciones
pueden ser asíncronas, realizadas al mismo tiempo o más tarde,
como procesamiento de backend (por ejemplo, el procesador de
eventos Bidder Tracker (Seguimiento de Postores)). Cuando un
postor realiza una puja, el procesador de eventos Bid Capture
(Captura de Pujas) recibe ese evento iniciador, determina si es más
alto que la puja anterior y activa un evento de bid placed (puja
realizada). El procesador de eventos Auctioneer (Subastador)
responde a ese evento y actualiza el sitio web con el nuevo precio
de puja del artículo. Simultáneamente, el procesador de eventos Bid

502Streamer (Transmisor de Pujas) responde al mismo evento,
transmitiendo la puja al historial de pujas del sitio web o incluso a
los postores individuales (dependiendo de la interfaz de usuario).
Finalmente, el procesador de eventos Bidder Tracker (Seguimiento
de Postores) responde al evento para persistir al postor y su puja
con fines de seguimiento y auditoría.

Esta  ilustración  muestra  el  flujo  de  un  sistema  de  subastas  en  línea  basado  en

eventos, donde un usuario inicia el proceso con el mensaje "Ofrezco 100 dólares

por ese artículo". Esta acción llega al servicio de captura de ofertas, el cual genera

un  evento  de  oferta  realizada  que  se  distribuye  de  forma  asíncrona  hacia  tres

componentes  distintos.  Primero,  el  servicio  de  subastador  y  el  servicio  de

transmisión de ofertas reciben la notificación para actualizar en tiempo real el sitio

web  de  subastas.  Simultáneamente,  el  servicio  de  seguimiento  de  postores

procesa  el  evento  para  registrar  la  actividad  en  la  base  de  datos,  demostrando

cómo  una  sola  acción  del  usuario  activa  múltiples  procesos  independientes  y

paralelos. (Accesibilidad de la imagen)

Figura 15-40. Ejemplo de un sistema de pujas en línea usando EDA

Muchos otros procesadores de eventos están involucrados en el flujo
de trabajo de este evento iniciador, y se activan muchos otros
eventos derivados, pero esta pequeña parte del sistema demuestra
un buen uso del estilo arquitectónico orientado a eventos, ilustrando
la capacidad de respuesta, la tolerancia a fallos, la escalabilidad y la
elasticidad.

503La arquitectura orientada a eventos es un estilo arquitectónico muy
complicado, pero también muy potente. Analiza detenidamente los
flujos de trabajo y el procesamiento necesarios para el problema de
negocio para determinar si lidiar con la complejidad de la EDA vale la
pena dados sus superpoderes. Si la mayoría del procesamiento
necesario se basa en solicitudes, considera en su lugar el estilo
arquitectónico de microservicios (analizado en el Capítulo 18).


697Parte III. Técnicas y
habilidades blandas

Un arquitecto de software eficaz no solo debe comprender los
aspectos técnicos de la arquitectura de software, sino también las
técnicas principales y las habilidades blandas necesarias para pensar
como un arquitecto, guiar a los equipos de desarrollo y comunicar
eficazmente la arquitectura a los diversos interesados. Esta sección
del libro aborda las técnicas y habilidades blandas clave que
necesitas para convertirte en un arquitecto de software eficaz.

698Capítulo 21. Decisiones
arquitectónicas

Una de las expectativas fundamentales de un arquitecto es tomar
decisiones arquitectónicas. Estas decisiones suelen involucrar la
estructura de la aplicación o del sistema, pero también pueden
incluir decisiones tecnológicas, especialmente cuando estas impactan
las características arquitectónicas. Independientemente del contexto,
una buena decisión arquitectónica es aquella que ayuda a guiar a los
equipos de desarrollo a elegir las opciones técnicas correctas. Tomar
decisiones arquitectónicas implica reunir suficiente información
relevante, justificar la decisión, documentarla y comunicarla de
manera efectiva a los interesados pertinentes.

Antipatrones en las decisiones arquitectónicas

El programador Andrew Koenig define un antipatrón como algo que
parece una buena idea al principio, pero que te mete en problemas.
Otra definición de antipatrón es un proceso repetible que produce
resultados negativos. Los tres antipatrones de decisión
arquitectónica más comunes que pueden surgir (y suelen hacerlo)
cuando un arquitecto toma decisiones son: el antipatrón de
"Cubrirse las espaldas" (Covering Your Assets), el antipatrón del "Día
de la marmota" (Groundhog Day) y el antipatrón de la "Arquitectura
impulsada por el correo electrónico" (Email-Driven Architecture).
Estos tres antipatrones suelen seguir un flujo progresivo: superar el
de "Cubrirse las espaldas" lleva al del "Día de la marmota", y superar
este último conduce al de la "Arquitectura impulsada por el correo
electrónico". Tomar decisiones arquitectónicas efectivas y precisas
requiere superar los tres.

699El antipatrón Covering Your Assets

El antipatrón "Covering Your Assets" (Cubrirse las espaldas) ocurre
cuando un arquitecto evita o pospone la toma de una decisión
arquitectónica por miedo a elegir la opción equivocada. Hay dos
formas de superar esto. La primera es esperar hasta el último
momento responsable para tomar una decisión arquitectónica
importante: es decir, cuando haya suficiente información para
justificar y validar la decisión, pero no tanto tiempo que detenga a
los equipos de desarrollo o meta al arquitecto en el antipatrón de la
Parálisis por análisis, donde se queda atrapado eternamente
analizando la decisión. Una buena forma de determinar el último
momento responsable es preguntarse cuándo el costo de posponer
la decisión supera el riesgo asociado con decidir. Como se ilustra en
la Figura 21-1, observa que en las primeras etapas de la escala de
tiempo para la toma de decisiones, el costo (denotado por la línea
sólida) es bajo porque se dedica menos tiempo a tomar la decisión,
pero el riesgo (denotado por la línea punteada) es alto porque se
sabe menos sobre el problema o la solución. Dedicar más tiempo a
posponer la decisión aumenta el costo, pero también reduce el
riesgo porque el arquitecto puede realizar un análisis más completo
del problema y las posibles alternativas. El momento de tomar una
decisión es donde estos dos factores se cruzan y el aumento del
costo supera la reducción del riesgo.

700Este gráfico ilustra la relación entre el riesgo y el costo al postergar una decisión

técnica a lo largo del tiempo. En el eje vertical se mide el nivel desde bajo hasta

alto, mientras que el eje horizontal representa el tiempo. Se observa que el riesgo,

representado  por  una  línea  punteada,  comienza  en  un  nivel  alto  y  disminuye  a

medida  que  se  obtiene  más  información;  por  el  contrario,  el  costo  de  retrasar  la

decisión, mostrado con una línea sólida, aumenta de forma constante. El punto de

intersección  entre  ambas  curvas,  señalado  con  una  flecha  como  el  momento  de

tomar  una  decisión,  representa  el  equilibrio  óptimo  o  el  último  momento

responsable,  donde  el  incremento  en  el  costo  de  esperar  comienza  a  superar  el

beneficio de la reducción del riesgo. (Accesibilidad de la imagen)

Figura 21-1. Último momento responsable

Otra forma de evitar este antipatrón es colaborar con los equipos de
desarrollo para asegurar que la decisión pueda implementarse según
lo esperado. Esto es vital porque ningún arquitecto puede conocer
cada detalle sobre cada problema asociado con una tecnología en
particular. Al colaborar estrechamente con los equipos de desarrollo,
puedes responder rápidamente, obtener más información y reducir
el riesgo de que la decisión sea incorrecta.

Para ilustrar este punto: supón que tú, como arquitecto, decides que
todos los datos de referencia relacionados con el producto (como
descripción, peso y dimensiones) deben almacenarse en caché en
todas las instancias de servicio que necesiten esa información.
Decides que esto se hará mediante una caché replicada de solo
lectura, siendo el servicio Catalog (Catálogo) el propietario de la

701caché primaria. (Una caché replicada o en memoria significa que si
hay cambios en la información del producto o se añaden nuevos
productos, el servicio Catalog actualiza su caché, la cual se replica
luego a todos los demás servicios que requieran esos datos a través
de un producto de caché replicada). Tu justificación para esta
decisión es reducir el acoplamiento entre los servicios y compartir
datos de manera efectiva sin tener que hacer una llamada entre
servicios. Sin embargo, los equipos de desarrollo que implementan
esta decisión arquitectónica descubren que, debido a los requisitos
de escalabilidad de algunos servicios, esta decisión requeriría más
memoria interna de la disponible. Como estás colaborando
estrechamente con estos equipos, te das cuenta rápidamente del
problema y ajustas tu decisión arquitectónica en consecuencia.

Antipatrón Groundhog Day

El antipatrón "Groundhog Day" (El día de la marmota) ocurre cuando
las personas no saben por qué un arquitecto tomó una decisión en
particular, por lo que siguen discutiéndola una y otra y otra vez, sin
llegar nunca a una resolución o acuerdo final. Recibe su nombre de
la película de 1993 Hechizo del tiempo (Groundhog Day), en la que
el personaje de Bill Murray debe revivir el 2 de febrero una y otra
vez, todos los días.

Este antipatrón ocurre porque los arquitectos no justifican su
decisión (o no la justifican por completo). Es importante
proporcionar tanto justificaciones técnicas como de negocio para una
decisión arquitectónica.

Por ejemplo, supongamos que decides dividir una aplicación
monolítica en servicios separados. Tu justificación es desacoplar los
aspectos funcionales de la aplicación para que cada parte utilice
menos recursos de la máquina virtual y pueda mantenerse y
desplegarse por separado. Aunque esta es una buena justificación
técnica, lo que falta es la justificación de negocio; en otras palabras,

702¿por qué debería el negocio pagar por esta refactorización
arquitectónica? Una buena justificación de negocio para esta
decisión podría ser entregar nuevas funcionalidades comerciales más
rápido, mejorando así el tiempo de salida al mercado. Otra podría
ser reducir los costos asociados con el desarrollo y lanzamiento de
nuevas características.

Proporcionar el valor de negocio es vital al justificar una decisión
arquitectónica. También es una buena prueba de fuego para
determinar si la decisión arquitectónica debe tomarse en primer
lugar. Si no aporta ningún valor de negocio, quizás deberías
reconsiderar la decisión.

Cuatro de las justificaciones de negocio más comunes son el costo,
el tiempo de salida al mercado, la satisfacción del usuario y el
posicionamiento estratégico. Considera qué es importante para los
interesados del negocio. Justificar una decisión particular basándose
únicamente en el ahorro de costos podría no ser la opción correcta si
los interesados están más preocupados por el tiempo de salida al
mercado.

Antipatrón Email-Driven Architecture

Una vez que un arquitecto toma y justifica plenamente sus
decisiones, a menudo surge otro antipatrón de arquitectura: la
Arquitectura Impulsada por Email (Email-Driven Architecture). Este
antipatrón ocurre cuando la gente pierde u olvida una decisión
arquitectónica, o incluso no sabe que se ha tomado y, por lo tanto,
no puede implementarla. Superar este antipatrón se trata de
comunicar las decisiones arquitectónicas de manera efectiva. El
correo electrónico es una herramienta de comunicación excelente,
pero es un sistema de repositorio de documentos deficiente.

Afortunadamente, un arquitecto puede evitar fácilmente el
antipatrón de la Arquitectura Impulsada por Email aprendiendo a
comunicar las decisiones arquitectónicas de manera efectiva.

703Primero, asegúrate de no incluir la decisión en el cuerpo de un
correo electrónico. Hacerlo crea múltiples sistemas de registro para
esa decisión, porque cada correo contiene una copia en lugar de
tenerla en un solo lugar. Muchos de esos correos omiten detalles
importantes sobre la decisión (incluyendo la justificación), lo que
provoca que surja de nuevo el antipatrón del Día de la Marmota.
Además, si esa decisión arquitectónica se cambia o se reemplaza, es
difícil saber si todas las personas relevantes recibieron la decisión
revisada.

Un mejor enfoque es mencionar solo la naturaleza y el contexto de
la decisión en el cuerpo del correo electrónico y proporcionar un
enlace al sistema de registro único, donde se almacenan la decisión
arquitectónica y los detalles correspondientes (ya sea un enlace a
una página wiki o una referencia a un documento en un sistema de
archivos).

Considera el siguiente correo electrónico sobre una decisión
arquitectónica:

“Hola, Sandra, he tomado una decisión importante sobre la
comunicación entre servicios que te afecta directamente. Por
favor, consulta la decisión en el siguiente enlace… .”

Observa que, en la redacción del principio de la primera frase, se
menciona el contexto (comunicación entre servicios), pero no la
decisión en sí. La segunda parte de la primera frase también es
importante: si una decisión arquitectónica no afecta directamente a
la persona, ¿para qué molestarla con eso? Esta es una excelente
prueba de fuego para determinar qué interesados (incluidos los
desarrolladores) deben ser notificados directamente de una decisión
arquitectónica. La segunda frase de este ejemplo proporciona un
enlace a la ubicación única de la decisión arquitectónica, ofreciendo
un sistema de registro único para las decisiones.

704Importancia arquitectónica

Muchos arquitectos creen que si una decisión involucra una
tecnología específica, entonces no es una decisión arquitectónica,
sino una decisión técnica. Esto no siempre es cierto. Si un arquitecto
decide utilizar una tecnología en particular porque respalda
directamente una característica arquitectónica específica (como el
rendimiento o la escalabilidad), entonces sigue siendo una decisión
arquitectónica.

Michael Nygard, un reconocido arquitecto de software y autor de la
segunda edición de Release It! (Pragmatic Bookshelf, 2018), aborda
el problema de qué decisiones deben ser responsabilidad de un
arquitecto (y, por lo tanto, qué constituye una decisión
arquitectónica) acuñando el término arquitectónicamente
significativo. Según Nygard, las decisiones arquitectónicamente
significativas son aquellas que afectan la estructura de un sistema,
sus características no funcionales, dependencias, interfaces o
técnicas de construcción.

Estructura, en este contexto, se refiere a las decisiones que afectan
los patrones o estilos de arquitectura que se están utilizando. Por
ejemplo, la decisión de un arquitecto de compartir código entre un
conjunto de microservicios impacta el contexto delimitado (bounded
context) del microservicio y, por lo tanto, afecta la estructura del
sistema.

Las características no funcionales del sistema son las características
arquitectónicas que son importantes para el sistema que se está
desarrollando o manteniendo. Por ejemplo, si la elección de una
tecnología afecta el rendimiento, y el rendimiento es un aspecto
importante de la aplicación, esa elección se convierte en una
decisión arquitectónica, aunque especifique un producto, marco de
trabajo (framework) o tecnología en particular.

Las dependencias se refieren a los puntos de acoplamiento entre
componentes y/o servicios dentro del sistema. Las dependencias

705pueden afectar características de la arquitectura como la
escalabilidad, modularidad, agilidad, testabilidad, fiabilidad, etc., por
lo que las decisiones sobre las dependencias se convierten en
decisiones arquitectónicas.

Interfaces se refieren a cómo se accede y se orquestan los servicios
y componentes: generalmente a través de una puerta de enlace
(gateway), centro de integración (integration hub), bus de servicios
(service bus), adaptador o proxy de API. Tomar decisiones sobre las
interfaces suele implicar la definición de contratos, incluyendo
estrategias de versionado y obsolescencia. Las interfaces impactan a
otros que usan el sistema y, por lo tanto, son arquitectónicamente
significativas.

Finalmente, las técnicas de construcción se refieren a decisiones
sobre plataformas, marcos de trabajo (frameworks), herramientas e
incluso procesos que, aunque sean de naturaleza técnica, podrían
impactar algún aspecto de la arquitectura.

Registros de decisiones arquitectónicas

Una de las formas más efectivas de documentar las decisiones
arquitectónicas es a través de los Registros de Decisiones
Arquitectónicas (ADRs). Michael Nygard evangelizó por primera vez
los ADR en una entrada de blog de 2011, y en 2017, el
Thoughtworks Technology Radar recomendó la técnica para una
adopción generalizada.

Un ADR consiste en un archivo de texto corto (generalmente de una
a dos páginas) que describe una decisión arquitectónica específica.
Aunque los ADR pueden escribirse usando texto plano o en una
plantilla de página wiki, suelen escribirse en algún tipo de formato
de documento de texto, como AsciiDoc o Markdown.

También existen herramientas para gestionar los ADR. Nat Pryce,
coautor de Growing Object-Oriented Software, Guided by Tests

706(Addison-Wesley, 2009), ha escrito una herramienta de código
abierto llamada ADR Tools que proporciona una interfaz de línea de
comandos para gestionar los ADR, incluyendo esquemas de
numeración, ubicaciones y lógica de reemplazo. Micha Kops, un
ingeniero de software de Alemania, ofrece algunos excelentes
ejemplos sobre el uso de herramientas ADR para gestionar los
registros de decisiones arquitectónicas.

Estructura básica

La estructura básica de un ADR consta de cinco secciones
principales: Título, Estado, Contexto, Decisión y Consecuencias.
Normalmente añadimos dos secciones adicionales como parte de la
estructura básica: Cumplimiento (Compliance) y Notas. La sección
de Cumplimiento es un espacio para pensar y documentar cómo se
gobernará y aplicará la decisión arquitectónica (manualmente o
mediante funciones de aptitud automatizadas). La sección de Notas
es un espacio para incluir metadatos sobre la decisión, como el
autor, quién la aprobó, cuándo se creó, etc.

Está bien ampliar esta estructura básica (como se ilustra en la Figura
21-2) para incluir cualquier otra sección necesaria. Solo mantén la
plantilla consistente y concisa. Un buen ejemplo de esto podría ser
añadir una sección de Alternativas analizando todas las demás
soluciones posibles.

707Esta imagen muestra una plantilla sobre una hoja de papel amarillo con renglones

que  detalla  el  formato  para  un  Registro  de  Decisión  Arquitectónica.  El  esquema

comienza  con  el  encabezado  "Formato  de  Registro  de  Decisión  Arquitectónica"  y

se organiza en secciones claras: el "TÍTULO", donde debes poner una descripción

corta  que  establezca  la  decisión  de  arquitectura;  el  "ESTADO",  que  señala  si  el

proceso  es  propuesto,  aceptado  o  reemplazado;  el  "CONTEXTO",  que  cuestiona

qué te obliga a tomar esa decisión; la "DECISIÓN", que incluye la determinación y

su respectiva justificación; las "CONSECUENCIAS", para definir cuál es el impacto

de  dicha  resolución;  el  "CUMPLIMIENTO",  donde  explicas  cómo  garantizarás  que

708se acate la decisión; y por último, las "NOTAS", destinadas a los metadatos como

el autor y otros datos informativos. (Accesibilidad de la imagen)

Figura 21-2. Estructura básica de un ADR

Título

Los títulos de los ADR suelen estar numerados secuencialmente y
contienen una frase corta que describe la decisión arquitectónica.
Por ejemplo, el título de un ADR que describa la decisión de usar
mensajería asíncrona entre el servicio Order (Pedido) y el servicio
Payment (Pago) podría decir: “42. Uso de mensajería asíncrona entre
los servicios de Pedido y Pago”. El título debe ser corto y conciso,
pero lo suficientemente descriptivo para eliminar cualquier
ambigüedad sobre la naturaleza y el contexto de la decisión.

Estado

Cada ADR tiene uno de tres estados: Propuesto, Aceptado o
Reemplazado. El estado Propuesto significa que la decisión debe ser
aprobada por alguien con mayor nivel de decisión o algún tipo de
organismo de gobierno de arquitectura (como un comité de revisión
de arquitectura). Aceptado significa que la decisión ha sido aprobada
y está lista para su implementación. Reemplazado significa que la
decisión ha sido cambiada y sustituida por otro ADR. El estado
Reemplazado siempre asume que el estado del ADR anterior era
Aceptado; en otras palabras, un ADR Propuesto nunca sería
reemplazado por otro ADR; sería modificado hasta ser Aceptado.

El estado Reemplazado es una forma poderosa de mantener
registros históricos de qué decisiones se han tomado, por qué se
tomaron en ese momento, cuál es la nueva decisión y por qué se
cambió. Normalmente, cuando un ADR ha sido reemplazado, se
marca con el número de la decisión que lo sustituyó. Del mismo
modo, la decisión que reemplaza a otro ADR se marca con el
número del ADR al que sustituyó.

709Por ejemplo, supongamos que el ADR 42 (“Uso de mensajería
asíncrona entre los servicios de Pedido y Pago”) está en estado
Aprobado. Debido a cambios posteriores en la implementación y
ubicación del servicio Payment (Pago), decides que ahora se debe
usar REST entre los dos servicios. Por lo tanto, creas un nuevo ADR
(número 68) para documentar este cambio de decisión. Los estados
correspondientes se verían de la siguiente manera:

ADR 42. Uso de mensajería asíncrona entre los servicios de Pedido
y Pago

Estado: Reemplazado por el 68

ADR 68. Uso de REST entre los servicios de Pedido y Pago

Estado: Aceptado, reemplaza al 42

El enlace y el rastro histórico entre los ADR 42 y 68 te permite evitar
la inevitable pregunta de "¿qué tal si usamos mensajería?" con
respecto al ADR 68.

710ADRS Y SOLICITUD DE COMENTARIOS (RFC)

Enviar un borrador de ADR o comentarios puede ayudar a un
arquitecto a validar sus suposiciones y afirmaciones con una
audiencia más amplia de interesados. Una forma efectiva de
involucrar a los desarrolladores e iniciar la colaboración es crear
un nuevo tipo de estado llamado Solicitud de Comentarios (RFC,
por sus siglas en inglés) y especificar una fecha límite para que
los revisores completen sus comentarios. Una vez alcanzada esa
fecha, el arquitecto puede analizar los comentarios, realizar los
ajustes necesarios a la decisión, tomar la decisión final y
establecer el estado en Propuesto (o Aceptado, si el arquitecto
tiene autoridad para aprobar la decisión).

Un ADR con estado RFC se vería de la siguiente manera:

ESTADO
Solicitud de comentarios, fecha límite 09 ENE 2026

Otro aspecto significativo de la sección de Estado de un ADR es que
obliga al arquitecto y a su jefe o arquitecto principal a discutir los
criterios para aprobar una decisión arquitectónica y determinar si el
arquitecto puede hacerlo por su cuenta, o si debe ser aprobada por
un arquitecto de mayor nivel, un comité de revisión de arquitectura
u otro organismo de gobierno.

Tres buenos puntos de partida para estas conversaciones son el
costo, el impacto entre equipos y la seguridad. El costo debe incluir
las tarifas de compra o licencia de software, los costos de hardware
adicional y el nivel de esfuerzo general para implementar la decisión
arquitectónica. Para estimar esto, multiplica el número estimado de
horas para implementar la decisión arquitectónica por la tasa
estándar de equivalencia a tiempo completo (FTE, por sus siglas en
inglés) de la empresa. El propietario o el gerente del proyecto suelen
tener el monto del FTE. Esta conversación podría llevar a que todos
acuerden que, por ejemplo, si el costo de la decisión arquitectónica

711supera cierta cantidad, entonces debe establecerse en un estado de
Propuesto y ser aprobada por alguien más. Si la decisión
arquitectónica afecta a otros equipos o sistemas, o tiene algún tipo
de implicación de seguridad, entonces debe ser aprobada por un
organismo de gobierno de nivel superior o un arquitecto principal.

Una vez que el equipo establezca y acuerde los criterios y los límites
correspondientes (como "los costos que superen los 5,000 dólares
deben ser aprobados por el comité de revisión de arquitectura"),
documéntalo bien para que todos los arquitectos que creen ADR
sepan cuándo pueden y cuándo no pueden aprobar sus propias
decisiones arquitectónicas.

Contexto

La sección de Contexto de un ADR especifica las fuerzas en juego.
En otras palabras, "¿Qué situación me obliga a tomar esta
decisión?". Esta sección del ADR permite al arquitecto describir las
circunstancias específicas y elaborar de forma concisa las posibles
alternativas. Si se requiere que el arquitecto documente en detalle el
análisis de cada alternativa, añade una sección de Alternativas en
lugar de incluir ese análisis en la sección de Contexto.

La sección de Contexto también ofrece un lugar para documentar un
área específica de la propia arquitectura. Al describir el contexto, el
arquitecto también está describiendo la arquitectura. Siguiendo el
ejemplo de la sección anterior, la sección de Contexto podría decir lo
siguiente: “El servicio de Pedido (Order) debe pasar información al
servicio de Pago (Payment) para pagar un pedido que se está
realizando actualmente. Esto podría hacerse mediante REST o
mensajería asíncrona”. Observa que esta declaración concisa
especifica no solo el escenario, sino también las alternativas
consideradas.

712Decisión

La sección de Decisión del ADR contiene una descripción de la
decisión arquitectónica, junto con una justificación completa. Nygard
recomienda expresar las decisiones arquitectónicas con una voz
afirmativa y de mando en lugar de una pasiva. Por ejemplo, la
decisión de usar mensajería asíncrona entre servicios diría:
“Usaremos mensajería asíncrona entre servicios”. Esto es mucho
mejor que “Creo que la mensajería asíncrona entre servicios sería la
mejor opción”, lo cual no deja claro cuál es la decisión ni si se ha
tomado alguna, solo la opinión del arquitecto.

Uno de los aspectos más potentes de la sección de Decisión de los
ADR es que permite al arquitecto enfatizar la justificación de la
decisión. Entender por qué se tomó una decisión es mucho más
importante que entender cómo funciona algo. Esto ayuda a los
desarrolladores y a otros interesados a comprender mejor el
razonamiento detrás de una decisión y, por lo tanto, hace que sea
más probable que estén de acuerdo con ella.

Para ilustrar este punto, supongamos que decides usar la Llamada a
Procedimiento Remoto de Google (gRPC) para comunicarte entre
dos servicios en particular para reducir la latencia de red debido a
necesidades de respuesta muy altas. Varios años después, un nuevo
arquitecto en el equipo decide usar REST en lugar de gRPC para que
las comunicaciones entre servicios sean más consistentes. Debido a
que el nuevo arquitecto no entiende por qué se eligió gRPC en
primer lugar, su decisión termina teniendo un impacto significativo
en la latencia, causando tiempos de espera (timeouts) en los
sistemas ascendentes. Si el nuevo arquitecto hubiera tenido acceso a
un ADR, habría entendido que la decisión original de usar gRPC tenía
como objetivo reducir la latencia (a costa de servicios estrechamente
acoplados) y podría haber evitado este problema.

713Consecuencias

Cada decisión que toma un arquitecto tiene algún tipo de impacto,
bueno o malo. La sección de Consecuencias de un ADR obliga al
arquitecto a describir el impacto general de una decisión
arquitectónica, permitiéndole reflexionar sobre si los impactos
negativos superan los beneficios.

Esta sección también es un buen lugar para documentar el análisis
de compensaciones (trade-offs) realizado durante el proceso de
toma de decisiones. Por ejemplo, supongamos que decides usar
mensajería asíncrona (fire-and-forget) para publicar reseñas en un
sitio web. Tu justificación para esta decisión es mejorar la capacidad
de respuesta (de 3,100 milisegundos a 25 milisegundos) porque los
usuarios no tendrían que esperar a que se publique la reseña real,
sino solo a que el mensaje se envíe a una cola. Un miembro de tu
equipo de desarrollo argumenta que es una mala idea debido a la
complejidad del manejo de errores asociado con una solicitud
asíncrona: "¿Qué pasa si alguien publica una reseña con malas
palabras?". Lo que este miembro del equipo no sabe es que tú
discutiste ese mismo problema con los interesados del negocio y
otros arquitectos al analizar las compensaciones de esta decisión, y
decidieron juntos que era mejor mejorar la capacidad de respuesta y
lidiar con el manejo de errores complejo en lugar de aumentar el
tiempo de espera y proporcionar retroalimentación sobre si la
publicación de la reseña fue exitosa o no. Si esta decisión se hubiera
documentado mediante un ADR, habrías podido proporcionar este
análisis de compensaciones en la sección de Consecuencias,
evitando este tipo de desacuerdo.

Cumplimiento

La sección de Cumplimiento (Compliance) no es una de las secciones
estándar de un ADR, pero es una que recomendamos
encarecidamente añadir. La sección de Cumplimiento establece cómo
se medirá y gobernará la decisión arquitectónica. ¿La comprobación

714de cumplimiento para esta decisión será manual, o puede
automatizarse mediante una función de aptitud (fitness function)? Si
se puede automatizar, el arquitecto puede especificar cómo se
escribirá la función de aptitud, junto con cualquier otro cambio
necesario en la base de código para medir el cumplimiento de esta
decisión arquitectónica.

Por ejemplo, supongamos que tomas la decisión dentro de una
arquitectura tradicional de n capas (como se ilustra en la Figura 21-
3) de que todos los objetos compartidos utilizados por los objetos de
negocio en la capa de Negocio deben residir en la capa de Servicios
Compartidos para aislar y contener la funcionalidad compartida.

715Esta  imagen  ilustra  un  modelo  de  arquitectura  por  capas  compuesto  por  la  capa

de presentación, la capa de negocio, la capa de servicios, la capa de persistencia y

la capa de base de datos. Casi todos los niveles están señalados como cerrados,

con  la  excepción  de  la  capa  de  servicios,  la  cual  se  muestra  como  abierta.  Un

óvalo resalta una interacción específica en la que dos componentes situados en la

capa  de  negocio  apuntan  mediante  flechas  hacia  un  componente  en  la  capa  de

servicios,  lo  que  representa  una  decisión  de  diseño  sobre  cómo  se  relacionan  y

acceden estos elementos entre sí dentro de la jerarquía del sistema. (Accesibilidad

de la imagen)

Figura 21-3. Un ejemplo de una decisión arquitectónica

Esta decisión arquitectónica puede medirse y gobernarse utilizando
una serie de herramientas de automatización, incluyendo ArchUnit
en Java y NetArchTest en C#. Con ArchUnit en Java, la prueba
automatizada de la función de aptitud para esta decisión
arquitectónica podría verse así:

@Test
public void shared_services_should_reside_in_services_layer() {
    classes().that().areAnnotatedWith(SharedService.class)
        .should().resideInAPackage("..services..")

716        .check(myClasses);
}

Esta función de aptitud automatizada requeriría escribir nuevas
historias para crear una anotación de Java (@SharedService) y
añadirla a todas las clases compartidas para soportar este método
de gobierno.

Notas

Otra sección que no forma parte de un ADR estándar pero que
recomendamos encarecidamente añadir es la sección de Notas. Esta
sección incluye varios metadatos sobre el ADR:

Autor original

Fecha de aprobación

Aprobado por

Fecha de reemplazo

Fecha de última modificación

Modificado por

Última modificación

Incluso cuando guardas los ADR en un sistema de control de
versiones (como Git), es útil tener metadatos adicionales más allá de
lo que el repositorio puede soportar. Recomendamos añadir esta
sección independientemente de cómo y dónde almacenes los ADR.

Ejemplo

Nuestro ejemplo del sistema de subastas Going, Going, Gone (GGG)
incluye docenas de decisiones arquitectónicas. Dividir las interfaces
de usuario del postor y del subastador, usar una arquitectura híbrida
que consista en microservicios y eventos, aprovechar el Protocolo de

717Transporte en Tiempo Real (RTP, por sus siglas en inglés) para la
captura de video, usar un único API Gateway y usar colas separadas
para la mensajería son solo algunas de las decisiones arquitectónicas
que un arquitecto tomaría. Cada decisión arquitectónica que un
arquitecto tome, por muy obvia que parezca, debe ser documentada
y justificada.

La Figura 21-4 ilustra una de las decisiones arquitectónicas dentro
del sistema de subastas GGG: usar colas punto a punto separadas
entre los servicios de captura de pujas (bid capture), transmisor de
pujas (bid streamer) y rastreador de pujas (bid tracker) en lugar de
un único tema de publicación y suscripción (o incluso REST, para el
caso).

718Este diagrama de arquitectura detalla el flujo de información dentro de un sistema

de subastas, comenzando con la entrada de ofertas hacia el servicio de captura de

ofertas.  Desde  este  punto,

los  datos  se  distribuyen  mediante  canales

independientes hacia dos procesos distintos: el servicio de transmisión de ofertas,

que se encarga de comunicar quién es el ganador, y el servicio de seguimiento de

ofertas,  que  transfiere  los  registros  a  una  base  de  datos  de  ofertas.  El  uso  de

líneas  punteadas  y  cilindros  horizontales  ilustra  cómo  las  comunicaciones  se

gestionan de forma asíncrona a través de colas de mensajes separadas para cada

función específica del sistema. (Accesibilidad de la imagen)

Figura 21-4. Uso de pub/sub entre servicios

Sin un ADR que justifique esta decisión, otras personas involucradas
en el diseño y desarrollo de este sistema podrían no estar de
acuerdo y decidir implementarlo de una manera diferente.

A continuación se presenta un ejemplo de un ADR para esta decisión
arquitectónica:

719ADR 76. Colas separadas para los servicios de Transmisión
de Pujas (Bid Streamer) y Rastreo de Postores (Bidder
Tracker)

ESTADO
Aceptado

CONTEXTO
El servicio Bid Capture (Captura de Pujas), al recibir una puja,
debe reenviarla al servicio Bid Streamer y al servicio Bidder
Tracker. Esto podría hacerse mediante un único tema (pub/sub),
colas separadas (punto a punto) para cada servicio, o REST a
través de la capa API de Subastas en Línea.

DECISIÓN
Usaremos colas separadas para los servicios Bid Streamer y
Bidder Tracker.

El servicio Bid Capture no necesita ninguna información del
servicio Bid Streamer ni del servicio Bidder Tracker (la
comunicación es solo en un sentido).

El servicio Bid Streamer debe recibir las pujas en el orden exacto
en que fueron aceptadas por el servicio Bid Capture. El uso de
mensajería y colas garantiza automáticamente el orden de las
pujas para la transmisión aprovechando las colas FIFO (primero en
entrar, primero en salir).

Entran múltiples pujas por el mismo monto (por ejemplo, "¿Oigo
cien?"). El servicio Bid Streamer solo necesita la primera puja
recibida para ese monto, mientras que el Bidder Tracker necesita
todas las pujas recibidas. El uso de un tema (pub/sub) requeriría
que el Bid Streamer ignore las pujas que sean iguales al monto
anterior, obligando al Bid Streamer a almacenar un estado
compartido entre instancias.

El servicio Bid Streamer almacena las pujas de un artículo en un
caché en memoria, mientras que el Bidder Tracker las almacena

720en una base de datos. Por lo tanto, el Bidder Tracker será más
lento y podría requerir contrapresión (backpressure). El uso de
una cola dedicada para Bidder Tracker proporciona este punto de
contrapresión dedicado.

CONSECUENCIAS
Requeriremos clustering y alta disponibilidad de las colas de
mensajes.

Esta decisión requerirá que el servicio Bid Capture envíe la misma
información a múltiples colas.

Los eventos de puja internos eludirán las comprobaciones de
seguridad realizadas en la capa API.
ACTUALIZACIÓN: Tras la revisión en la reunión del ARB (Comité
de Revisión de Arquitectura) del 14 de enero de 2025, el ARB
decidió que esta era una compensación aceptable y que no se
necesitan comprobaciones de seguridad adicionales para los
eventos de puja entre estos servicios.

CUMPLIMIENTO
Realizaremos revisiones manuales periódicas del código para
asegurar que se está utilizando la mensajería pub/sub asíncrona
entre los servicios Bid Capture, Bid Streamer y Bidder Tracker.

NOTAS
Autor: Subashini Nadella

Aprobado por: Miembros de la reunión del ARB, 14 ENE 2025

Última actualización: 14 ENE 2025

Almacenamiento de los ADR

Una vez que un arquitecto crea un ADR, necesita guardarlo en algún
lugar. Independientemente de dónde sea, cada decisión
arquitectónica debe tener su propio archivo o página de wiki. A
algunos arquitectos les gusta mantener los ADR en el mismo

721repositorio de Git que el código fuente, lo que permite al equipo
versionar y rastrear los ADR como lo harían con el código fuente.

Sin embargo, para las organizaciones más grandes, advertimos
contra esta práctica por varias razones. En primer lugar, es posible
que no todos los que necesiten ver la decisión arquitectónica tengan
acceso al repositorio de Git que contiene los ADR. En segundo lugar,
el repositorio de Git de la aplicación no es un buen lugar para
almacenar los ADR que tienen un contexto ajeno a ellos (como
decisiones arquitectónicas de integración, decisiones arquitectónicas
empresariales o decisiones que son comunes a todas las
aplicaciones). Por estas razones, recomendamos almacenar los ADR
en un repositorio de Git exclusivo para ADR al que todos tengan
acceso, en una wiki (usando una plantilla de wiki) o en un directorio
compartido en un servidor de archivos al que se pueda acceder
fácilmente mediante una wiki u otro software de renderizado de
documentos.

La Figura 21-5 muestra cómo podría verse esta estructura de
directorios (o la estructura de navegación de una página de wiki).

722Esta  imagen  muestra  un  diagrama  de  la  estructura  jerárquica  de  carpetas  para

organizar  documentos,  donde  el  directorio  principal  se  titula  decisiones  de

723arquitectura.  De  esta  raíz  se  desprenden  tres  categorías  principales:  aplicación,

integración y empresarial. A su vez, la carpeta de aplicación se subdivide en otras

tres carpetas llamadas común, aplicación 1 y aplicación 2. El diseño emplea iconos

de  carpetas  azules  conectados  por  líneas  negras  que  representan  visualmente  la

organización y subordinación de cada nivel dentro de un sistema de archivos para

el almacenamiento de registros. (Accesibilidad de la imagen)

Figura 21-5. Ejemplo de estructura de directorios para almacenar ADR

El directorio application contiene decisiones arquitectónicas que son
específicas de algún tipo de contexto de aplicación (o producto).
Este directorio se subdivide en otros directorios:

common (común)

El subdirectorio common es para las decisiones
arquitectónicas que se aplican a todas las aplicaciones, como
por ejemplo: "Todas las clases relacionadas con el
framework contendrán una anotación (@Framework en
Java) o atributo ([Framework] en C#) que identiﬁque la clase
como perteneciente al código del framework subyacente".

application (aplicación)

Los subdirectorios bajo el directorio application
corresponden al contexto especíﬁco de la aplicación o
sistema y contienen decisiones arquitectónicas propias de
esa aplicación o sistema (en este ejemplo, las aplicaciones
app1 y app2).

integration (integración)

El directorio integration contiene los ADR que involucran la
comunicación entre aplicaciones, sistemas o servicios.

enterprise (empresa)

724Los ADR de arquitectura empresarial se encuentran dentro
del directorio enterprise, indicando que se trata de
decisiones arquitectónicas globales que impactan a todos los
sistemas y aplicaciones. Un ejemplo de un ADR de
arquitectura empresarial sería: "Todo acceso a una base de
datos del sistema se realizará únicamente desde el sistema
propietario", evitando que las bases de datos se compartan
entre múltiples sistemas.

Cuando guardas los ADR en una wiki, se aplica la misma estructura,
donde cada estructura de directorio representa una página de
destino de navegación. Cada ADR se representa como una única
página de wiki dentro de cada página de destino de navegación
(aplicación, integración o empresa).

Los nombres de los directorios y de las páginas de destino indicados
en esta sección son solo recomendaciones y ejemplos. Elige los
nombres que mejor se adapten a la situación de tu empresa,
siempre que esos nombres sean consistentes entre los equipos.

Los ADR como documentación

Documentar la arquitectura de software siempre ha sido difícil. Si
bien están surgiendo algunos estándares para diagramar la
arquitectura (como el Modelo C4 del arquitecto de software Simon
Brown o el estándar ArchiMate de The Open Group), no existe un
estándar acordado para documentar la arquitectura de software. Ahí
es donde entran los ADR.

Los ADR pueden ser un medio eficaz para documentar una
arquitectura de software. La sección de Contexto ofrece una
excelente oportunidad para describir el área específica del sistema
que requiere que se tome una decisión arquitectónica, así como para
describir las alternativas. Más importante aún, la sección de Decisión
describe las razones por las que se toma una decisión particular, lo

725cual es, con mucho, la mejor forma de documentación
arquitectónica. La sección de Consecuencias añade la pieza final del
rompecabezas al describir el análisis de compensaciones (trade-offs)
para la decisión; por ejemplo, las razones (y compensaciones) para
elegir el rendimiento sobre la escalabilidad.

Uso de los ADR para estándares

A muy pocos desarrolladores les gustan los estándares.
Desafortunadamente, a veces los estándares tienen más que ver con
el control que con proporcionar un propósito útil. Usar los ADR para
los estándares puede cambiar esta mala práctica. Por ejemplo, la
sección de Contexto de un ADR describe la situación que está
obligando a la organización a adoptar ese estándar en particular. La
sección de Decisión de un ADR puede indicar así no solo cuál es el
estándar, sino más importante aún, por qué necesita existir.

Esta es una excelente manera de evaluar si un estándar en particular
debería existir en primer lugar. Si un arquitecto no puede justificarlo,
entonces quizás no sea un buen estándar para establecer y hacer
cumplir. Además, cuanto más entiendan los desarrolladores por qué
existe un estándar determinado, más probable será que lo sigan (y,
correspondientemente, que no lo cuestionen). La sección de
Consecuencias de un ADR es otro gran lugar para evaluar si un
estándar es válido: requiere que el arquitecto piense y documente
las implicaciones y consecuencias del estándar, y si ese estándar en
particular debe implementarse o no.

Uso de los ADR con sistemas existentes

Muchos arquitectos cuestionan la utilidad de los ADR para los
sistemas existentes. Después de todo, las decisiones arquitectónicas
ya se han tomado y el sistema está en producción. ¿Tienen los ADR
algún propósito real en este punto? De hecho, sí lo tienen.
Recuerda, los ADR son más que una simple documentación: ayudan

726a los arquitectos y desarrolladores a entender por qué se tomó una
decisión y si fue la más adecuada.

Empieza escribiendo algunos ADR para las decisiones arquitectónicas
más significativas que se hayan tomado y cuestiona si esas
decisiones son las correctas o no. Por ejemplo, tal vez un grupo de
servicios esté compartiendo una única base de datos. ¿Por qué?
¿Hay una buena razón? ¿Deberían separarse los datos?

Parte del camino de incorporar los ADR en un sistema existente
consiste en realizar un pequeño trabajo de investigación para
descubrir estos interrogantes sobre el porqué. Desafortunadamente,
la persona que tomó la decisión original podría haberse ido de la
empresa hace mucho tiempo, por lo que nadie conoce la respuesta.
En estos casos, corresponde al arquitecto identificar y analizar las
alternativas y las compensaciones de cada opción e intentar validar
(o invalidar) la decisión existente. En cualquier caso, escribir ADR
para este tipo de decisiones significativas comienza a construir las
justificaciones y los razonamientos (y el acervo de conocimientos)
para el sistema y puede ayudar a identificar ineficiencias
arquitectónicas y diseños de sistema incorrectos.

Aprovechamiento de la IA generativa y los LLM
en las decisiones arquitectónicas

Uno de los muchos aspectos intrigantes de la IA generativa es si los
arquitectos pueden utilizarla para ayudar a tomar y validar
decisiones. ¿Deberían los servicios usar mensajería, streaming o
event sourcing al enviar datos río abajo? ¿Debería la base de datos
permanecer como un único monolito o debería dividirse en bases de
datos de dominio? ¿Debería Payment Processing (Procesamiento de
Pagos) desplegarse como un servicio único o dividirse en múltiples
servicios, uno por cada tipo de pago?

La mayoría de los arquitectos ya conocen la respuesta a estas
preguntas: ¡depende! Volviendo a nuestra Primera Ley de la

727Arquitectura de Software, todo en la arquitectura de software es una
compensación. Decisiones como estas dependen de muchos
factores, incluido el contexto específico en el que se aplica la
decisión. Cada situación y cada entorno es diferente, por lo que no
existen "mejores prácticas" para este tipo de cuestiones
estructurales.

La mayoría de los LLM basan sus resultados principalmente en la
probabilidad. En otras palabras, ¿cuál es la respuesta más probable
dado el contexto del prompt y cuál es la "mejor práctica" para este
problema? Sin embargo, la probabilidad y las "mejores prácticas" no
tienen cabida al tomar decisiones arquitectónicas. Responder a
preguntas arquitectónicas requiere un análisis cuidadoso de las
compensaciones involucradas y la aplicación de un contexto técnico
y de negocio específico para identificar la opción más adecuada. Por
ejemplo, si al negocio le preocupa más el tiempo de salida al
mercado (hacer llegar los cambios y las nuevas funcionalidades a los
clientes lo más rápido posible), entonces la mantenibilidad será
mucho más importante que el rendimiento, y guiará la mayor parte
del proceso de toma de decisiones hacia la optimización de la
mantenibilidad.

Las decisiones arquitectónicas requieren traducir las preocupaciones
del negocio (como el tiempo de salida al mercado o el crecimiento
sostenido) en características arquitectónicas (como mantenibilidad,
capacidad de prueba, capacidad de despliegue, etc.). Esta traducción
no siempre es obvia y lograrla correctamente requiere años de
experiencia. Una vez completada, sirve como base para el análisis de
compensaciones. Por ejemplo, decidir si tener un único servicio para
el procesamiento de pagos o un servicio por tipo de pago se reduce
a una compensación entre mantenibilidad y rendimiento: un único
servicio ofrece un mejor rendimiento, pero múltiples servicios
ofrecen una mejor mantenibilidad. Si al negocio le preocupa
principalmente el tiempo de salida al mercado, la mantenibilidad es

728mucho más importante que el rendimiento, por lo que servicios
separados serían la opción adecuada para este contexto específico.

Debido a la naturaleza tan específica e individualista del análisis de
compensaciones y del contexto de negocio, es difícil que la IA
generativa, tal como existe actualmente, llegue a la decisión
arquitectónica más adecuada. El mejor de los casos, basado en
experimentos recientes que tus autores han realizado, es que una
herramienta de IA generativa esquematice las posibles
compensaciones de una decisión, para ayudar a identificar cualquier
compensación que se haya pasado por alto. Si bien las herramientas
de IA generativa tienen mucho conocimiento, carecen de la sabiduría
necesaria para tomar la decisión arquitectónica más apropiada.


846Capítulo 26. Intersecciones
arquitectónicas

Hasta ahora en este libro, te hemos mostrado cómo identificar las
características críticas que una arquitectura debe soportar, cómo
seleccionar el estilo arquitectónico más apropiado para esas
características y para el problema de negocio, cómo tomar
decisiones de arquitectura efectivas y cómo liderar y guiar a los
equipos de desarrollo a través de la implementación de la
arquitectura. Sin embargo, para que una arquitectura funcione,
también debe estar alineada con otras facetas del entorno técnico y
de negocio. A estas alineaciones las llamamos las intersecciones de
la arquitectura.

En este capítulo, analizamos varias intersecciones importantes que
surgen al crear o validar una arquitectura de software:

Implementación

¿Está la implementación alineada con las preocupaciones
arquitectónicas que rodean las características operativas, las
restricciones arquitectónicas y la estructura interna de la
arquitectura?

Infraestructura

¿Se alinean la infraestructura y la forma en que se despliega
la arquitectura con las preocupaciones operativas de la
misma, como la escalabilidad, la capacidad de respuesta, la
tolerancia a fallos y la disponibilidad?

Topologías de datos

847Una alineación ampliamente ignorada es la que existe en la
intersección entre la arquitectura y las topologías de datos y
el tipo de datos. La topología de datos (monolítica, bases de
datos de dominio y base de datos por servicio) debe
alinearse correctamente con el estilo arquitectónico para
que el sistema funcione.

Prácticas de ingeniería

¿Coincide la forma en que el equipo de desarrollo crea,
mantiene y prueba el software con la arquitectura
correspondiente? ¿Coincide el pipeline de despliegue con el
estilo arquitectónico?

Topologías de equipo

La forma en que se organizan los equipos puede impactar
signiﬁcativamente la arquitectura, y viceversa. Si la
estructura del equipo no está debidamente alineada con la
arquitectura, los equipos de desarrollo por lo general
tendrán diﬁcultades, encontrando desaﬁantes incluso los
cambios más simples.

Integración de sistemas

¿Con qué otros sistemas o servicios necesita comunicarse la
arquitectura? No prestar atención a esta intersección en
particular puede tener resultados devastadores en términos
de mantenimiento, ﬁabilidad y características operativas
como la escalabilidad, la capacidad de respuesta y la
disponibilidad.

La empresa

¿Está la arquitectura alineada con los frameworks, prácticas,
principios rectores y estándares de toda la organización y la
empresa?

848El entorno de negocio

¿Está la arquitectura debidamente alineada con el entorno
de negocio y el dominio del problema? Con demasiada
frecuencia los arquitectos ignoran esta importante
intersección y, como resultado, la arquitectura no logra
cumplir con los objetivos o necesidades del negocio.

IA generativa

¿Cómo impacta en la arquitectura el uso cada vez mayor de
los modelos de lenguaje extensos (LLM)? Esta intersección se
está convirtiendo rápidamente en una muy importante a
medida que más empresas aprovechan la IA generativa
dentro de sus sistemas.

Las siguientes secciones describen estas intersecciones con más
detalle.

Arquitectura e implementación

La primera ley de la arquitectura de software también resulta ser la
respuesta más común de los arquitectos de software a cualquier
pregunta: "Depende". Quizás la segunda respuesta más común es:
"Ese es un detalle de implementación". Cuando una arquitectura de
software no logra alcanzar sus objetivos, esta segunda respuesta
suele ser la culpable.

Para que una arquitectura funcione correctamente, su
implementación —es decir, su código fuente— debe estar alineada
con su diseño para abordar tres cosas: las preocupaciones
operativas de la arquitectura (como la tolerancia a fallos, la
capacidad de respuesta, la escalabilidad, etc.), la estructura interna
y las restricciones. Esta sección aborda cada una de las tres por
turno.

849Preocupaciones operativas

Las preocupaciones operativas son las características arquitectónicas
en las que nos centramos en la Parte I del libro, las cuales forman la
base de cualquier arquitectura de software y que la arquitectura
debe soportar para resolver el problema de negocio en cuestión. Las
características arquitectónicas son las que impulsan las decisiones
arquitectónicas (como se analizó en el Capítulo 21).

Entonces, ¿qué significa que la arquitectura y la implementación
dejen de estar alineadas en la forma en que abordan las
preocupaciones operativas del sistema? Supongamos que eres un
arquitecto que trabaja en un nuevo sistema de entrada de pedidos
que necesita soportar desde varios miles hasta medio millón de
clientes concurrentes. Eliges un estilo de arquitectura de
microservicios, basándote en las calificaciones de estrellas que se
encuentran en "Características del estilo" en el Capítulo 18, lo cual
es apropiado dadas las altas necesidades de escalabilidad y
elasticidad de este sistema. Sin embargo, durante la
implementación, el equipo de desarrollo observa que, debido a que
los contextos delimitados de los servicios están formados de manera
tan estricta (ver "Contexto delimitado" en el Capítulo 18), el servicio
Order Placement (Colocación de pedidos) no puede acceder
directamente a la base de datos de inventario. En su lugar, debe
llamar sincrónicamente al servicio Inventory (Inventario) para
obtener el inventario actual de cualquier artículo que un cliente esté
interesado en comprar. Esta llamada sincrónica no solo acopla
estrechamente los dos servicios, sino que ralentiza enormemente la
capacidad de respuesta del sistema.

El equipo de desarrollo decide utilizar un caché replicado en
memoria entre estos servicios, como se muestra en la Figura 26-1:
los datos residen en la memoria interna de cada instancia de servicio
y siempre se mantienen sincronizados en segundo plano mediante el
almacenamiento en caché. Los productos de almacenamiento en
caché para este propósito incluyen Apache Ignite y Hazelcast. Aquí,

850el servicio Inventory (Inventario) tendría un caché en memoria de
escritura que contiene los IDs de los artículos y los recuentos de
inventario actuales; cada instancia del servicio Order Placement
(Colocación de pedidos) tendría una versión replicada de solo
lectura de ese caché en su memoria interna. El uso de un caché
replicado en memoria desacopla los servicios y mejora
significativamente la capacidad de respuesta.

Este  diagrama  ilustra  la  arquitectura  de  integración  entre  los  servicios  de

Colocación de pedidos y Gestión de inventario. El sistema de Gestión de inventario

utiliza  una  caché  en  memoria  actualizable  que  almacena  datos  detallados  del

inventario,  como  el  identificador  del  artículo  y  sus  niveles  actuales,  máximos  y

mínimos. Esta información se replica hacia una caché de solo lectura ubicada en el

servicio de Colocación de pedidos, lo cual permite desacoplar ambos componentes

y  mejorar  la  velocidad  de  respuesta  al  consultar  las  cantidades  disponibles  sin

necesidad  de  acceder  directamente  a  la  base  de  datos  principal  de  inventario.

Aunque  este  diseño  optimiza  el  rendimiento  inicial,  el  flujo  de  datos  replicados

puede  generar  condiciones  de  falta  de  memoria  si  el  sistema  escala  de  manera

masiva. (Accesibilidad de la imagen)

Figura 26-1. El equipo de desarrollo decidió utilizar el almacenamiento en caché
replicado en memoria entre los servicios, lo que resultó en condiciones de falta de
memoria al escalar los servicios

851Tras el lanzamiento a producción, a medida que aumenta el número
de usuarios concurrentes, se necesitan más instancias de cada
servicio para manejar la carga. El sistema colapsa cuando la carga
alcanza unos 80,000 clientes concurrentes porque los requisitos de
memoria del caché interno son demasiado altos, lo que provoca
condiciones de falta de memoria en todas las máquinas virtuales.

En este escenario, la arquitectura y su implementación están
desalineadas. Mientras que la arquitectura se centra en soportar
altos niveles de escalabilidad y elasticidad, la implementación se
centra en la capacidad de respuesta y el desacoplamiento de
servicios. Ambos equipos tomaron buenas decisiones, pero al
servicio de objetivos diferentes.

Integridad estructural

En el Capítulo 8 aprendiste que los componentes lógicos son los
bloques de construcción de cualquier sistema y forman su
arquitectura lógica. Generalmente se representan a través de las
estructuras de directorios en el repositorio de código fuente (o
namespaces, dependiendo del lenguaje de programación). Dado que
la arquitectura lógica describe cómo funciona el sistema y qué partes
del sistema interactúan con otras partes, es fundamental que la
estructura del código fuente coincida con la de la arquitectura lógica.

Sin la guía, el conocimiento y el gobierno adecuados, es fácil que los
desarrolladores ignoren la arquitectura lógica del sistema y
comiencen a crear estructuras de directorios y namespaces a su
antojo, sin tener en cuenta su impacto en la integridad del sistema.
Esta desalineación da como resultado arquitecturas que son difíciles
de mantener, probar y desplegar, y que, como resultado, se vuelven
menos fiables y más difíciles de evolucionar o adaptar a nuevas
funcionalidades, como la arquitectura lógica ilustrada en la Figura
26-2.

852Esta imagen representa un diagrama de una arquitectura lógica interna que carece

de  gobernanza  y  alineación,  mostrando  una  red  compleja  de  dependencias  entre

diversos  componentes.  En  el  área  dedicada  al  Suscriptor  se  encuentran  los

módulos de Información y Nuevo tique, mientras que el bloque del Tique incluye al

Experto,  la  Conexión  móvil  y  un  Flujo  de  trabajo  que  contiene  las  acciones  de

Enviar  tique  y  Cerrar  tique.  El  segmento  de  Finalización  agrupa  el  envío  de

encuestas  y  un  proceso  para  Cerrar  tique  que  emite  una  Notificación  por  correo

electrónico.  Finalmente,  elementos  como  el  Registro  y  el  Estado  del  tique

aparecen  vinculados  mediante  múltiples  flechas  de  dirección,  lo  que  ilustra  un

sistema altamente acoplado y difícil de mantener. (Accesibilidad de la imagen)

Figura 26-2. Un ejemplo de una arquitectura lógica interna que carece de gobierno
y alineación

Para asegurar que la estructura del código fuente coincida con la
arquitectura lógica, recomendamos el uso de herramientas de
gobierno automatizadas, como ArchUnit para la plataforma Java,
ArchUnitNet y NetArchTest para la plataforma .NET, PyTestArch para
Python, o TSArch para TypeScript y JavaScript. Estas herramientas
automatizadas, sumadas a una buena comunicación y colaboración

853entre el arquitecto y el equipo de desarrollo, crean implementaciones
que están debidamente alineadas con la arquitectura, como se
muestra en la Figura 26-3.

854Este  diagrama  ilustra  una  arquitectura  lógica  interna  compuesta  por  tres  áreas

principales:  Gestión  de  tickets,  Encuesta  al  cliente  y  Cliente.  En  la  sección  de

Gestión de tickets, el proceso inicia con la Creación de tickets, que fluye hacia la

Asignación  de  tickets;  desde  este  punto,  se  desprenden  conexiones  hacia  la

Notificación  al  cliente,  el  Estado  de  experto  y  el  Enrutamiento  de  tickets.  La

Notificación  al  cliente  conduce  a  la  Finalización  del  ticket,  la  cual  se  vincula  de

nuevo con el Estado de experto y activa el bloque de Enviar encuesta dentro del

área  de  Encuesta  al  cliente.  En  este  segundo  apartado,  tanto  el  envío  como  la

acción de Recibir encuesta se conectan con las Plantillas de encuestas. Finalmente,

el  área  de  Cliente  agrupa  de  manera  independiente  el  Registro  de  clientes  y  el

855Perfil  del  cliente,  mostrando  una  estructura  con  múltiples  interdependencias  y

flujos cruzados. (Accesibilidad de la imagen)

Figura 26-3. Un ejemplo de una arquitectura lógica interna basada en el gobierno
y la alineación adecuados

Compara la Figura 26-2 con la Figura 26-3. Observa cómo la
arquitectura de la Figura 26-3 es mucho más mantenible, testeable,
desplegable, fiable, adaptable y extensible que la de la arquitectura
desalineada mostrada en la Figura 26-2. Esta comparación ilustra la
importancia de este tipo de alineación en la implementación.

Restricciones arquitectónicas

Una restricción es una regla o principio de gobierno que describe
algún tipo de limitación dentro de la arquitectura (como restringir las
comunicaciones solo a REST o usar un tipo específico de base de
datos) necesaria para lograr sus objetivos. Si la implementación del
sistema no se adhiere a sus restricciones, la arquitectura fallará. Por
lo tanto, parte del trabajo de un arquitecto de software es identificar
y comunicar las restricciones de una arquitectura.

Para ilustrar a qué nos referimos con esta intersección en particular,
considera un negocio que intenta lanzar un nuevo sistema con un
presupuesto muy limitado y un plazo ajustado. Este negocio espera
muchos cambios estructurales en la base de datos y necesita que
esos cambios se realicen lo más rápido posible. En este caso, una
arquitectura por capas tradicional (ver el Capítulo 10) sería una
excelente opción debido a su simplicidad, rentabilidad y
particionamiento técnico. Debido a que este estilo separa las capas,
los cambios en la base de datos pueden aislarse en una sola capa,
haciéndolos más fáciles y rápidos.

Para que la arquitectura por capas funcione en este problema de
negocio en particular, el arquitecto necesitaría definir las siguientes
restricciones:

856Toda la lógica de la base de datos debe residir en la capa de
Persistencia.

La capa de Presentación no puede acceder directamente a la
capa de Persistencia, sino que debe pasar por todas las
capas, incluso para consultas simples.

Estas restricciones son necesarias para evitar que la lógica de la
base de datos se extienda por toda la arquitectura, y para que los
cambios en la estructura física de la base de datos (como eliminar
una tabla o cambiar el nombre de una columna) no afecten a ningún
código fuera de la capa de Persistencia.

Ahora supongamos que los desarrolladores de la interfaz de usuario
(UI) deciden que es más rápido llamar directamente a la base de
datos e implementan la arquitectura de esa manera. Además, los
desarrolladores del backend se dan cuenta de que sería mucho más
fácil mantener y probar el código si la lógica de negocio y la lógica
de la base de datos estuvieran juntas, por lo que también ignoran
las restricciones y acoplan estas preocupaciones en la capa de
negocio de la arquitectura. Esta implementación no está alineada
con las restricciones de la arquitectura, lo que significa que los
cambios en la base de datos afectarán a todo el código en cada
capa, tardarán demasiado y el sistema no cumplirá con los objetivos
de negocio.

Las herramientas arquitectónicas también son útiles para gobernar
las restricciones arquitectónicas.

Arquitectura e infraestructura

El alcance de la arquitectura de software ha crecido en las últimas
dos décadas para abarcar cada vez más responsabilidad y
perspectiva. A mediados de la década de 2000, la relación típica
entre la arquitectura y las operaciones era contractual y formal, con
mucha burocracia. La mayoría de las empresas subcontrataban las

857operaciones a un tercero para evitar la complejidad de alojar sus
propias operaciones, con acuerdos de nivel de servicio (SLA) para el
tiempo de actividad, la escala, la capacidad de respuesta y otras
características importantes. Hoy en día, sin embargo, los estilos de
arquitectura como los microservicios aprovechan libremente
características que solían ser puramente operativas. Por ejemplo, la
escala elástica solía estar integrada en las arquitecturas basadas en
el espacio (ver el Capítulo 16), pero hoy en día, los microservicios la
manejan de forma menos dolorosa gracias a una colaboración más
estrecha entre los arquitectos y DevOps.

858HISTORIA: CÓMO PETS.COM NOS DIO LA ESCALA
ELÁSTICA

La gente suele asumir que nuestras capacidades técnicas
actuales (como la escala elástica) simplemente son inventadas
un día por algún desarrollador ingenioso. En realidad, sin
embargo, las mejores ideas suelen nacer de lecciones difíciles.
Pets.com es un ejemplo temprano. Este sitio de comercio
electrónico apareció alrededor de 1998, con la esperanza de
convertirse en el Amazon.com de los suministros para mascotas.
Su brillante departamento de marketing creó una mascota
cautivadora: un títere de calcetín con un micrófono que decía
cosas irreverentes. La mascota se convirtió en una superestrella,
apareciendo en público en desfiles y eventos deportivos
nacionales.

Desafortunadamente, la gerencia de Pets.com aparentemente
gastó todo el dinero en la mascota, no en la infraestructura. Una
vez que los pedidos empezaron a llegar a raudales, no estaban
preparados. El sitio web era lento, las transacciones se perdían,
las entregas se retrasaban... fue prácticamente el peor de los
escenarios. Poco después de una desastrosa racha navideña,
Pets.com cerró, vendiendo su único activo valioso restante: la
mascota.

Lo que Pets.com necesitaba era escala elástica: la capacidad de
levantar más instancias de recursos cuando fueran necesarias.
Los proveedores de la nube ahora ofrecen esta funcionalidad
como algo estándar, pero las primeras empresas de comercio
electrónico tenían que gestionar su propia infraestructura, y
muchas fueron víctimas de un fenómeno hasta entonces
desconocido: el exceso de éxito puede matar a un negocio. La
caída de Pets.com, y otras historias de terror similares, llevaron a
los arquitectos a prestar más atención a tales intersecciones al
crear arquitecturas de software.

859La intersección entre la arquitectura y la infraestructura es
importante porque facilita las características arquitectónicas
operativas. Solo porque una arquitectura pueda soportar una alta
escalabilidad no significa que lo hará; si la infraestructura
correspondiente no lo soporta, no lo hará (como lo demostró
Pets.com). En los sitios de los clientes, con demasiada frecuencia
hemos sido testigos de cómo se culpa a los arquitectos y
desarrolladores de fallos arquitectónicos que en realidad fueron
causados por una desalineación entre la arquitectura y la
infraestructura.

En la mayoría de los casos, esta desalineación ocurre debido a una
falta de comunicación y colaboración entre el arquitecto y los
responsables de la infraestructura y las operaciones. Los arquitectos
a menudo no se dan cuenta de la influencia de la infraestructura en
características como la escalabilidad, la capacidad de respuesta, la
tolerancia a fallos, el rendimiento, la disponibilidad, la elasticidad,
etc. Esta desalineación dio origen al campo de DevOps.

Durante muchos años, muchas empresas consideraron que las
operaciones eran independientes del desarrollo de software,
subcontratándolas a menudo a una empresa externa como medida
de ahorro. En las décadas de 1990 y 2000, muchas arquitecturas se
diseñaron defensivamente partiendo del supuesto de que las
operaciones se subcontratarían y, por tanto, estarían fuera del
control de los arquitectos. (Para un buen ejemplo de esto, ver el
Capítulo 16). Sin embargo, a mediados de la década de 2000, las
empresas empezaron a experimentar con nuevas formas de
arquitectura que combinaban muchas preocupaciones operativas.
Por ejemplo, los estilos de arquitectura más antiguos, como la SOA
impulsada por la orquestación, requerían herramientas y frameworks
elaborados para soportar capacidades como la escalabilidad y la
elasticidad, lo que complicaba enormemente la implementación. Así
que los arquitectos crearon arquitecturas que podían manejar la
escala, el rendimiento, la elasticidad y una serie de otras

860capacidades internamente. El efecto secundario fue que estas
arquitecturas eran enormemente más complejas.

Los creadores del estilo de arquitectura de microservicios se dieron
cuenta de que las preocupaciones operativas se manejan mejor por
operaciones. Al crear una relación de colaboración entre la
arquitectura y las operaciones, los arquitectos se dieron cuenta de
que podían simplificar sus diseños y confiar en la gente de
operaciones para manejar las cosas que mejor manejan. Se
asociaron con operaciones para crear microservicios y para sentar
las bases de lo que se convertiría en el movimiento DevOps. Aunque
DevOps ha ayudado, esta intersección entre arquitectura e
infraestructura sigue siendo problemática para la mayoría de las
empresas.

Aunque la infraestructura es una preocupación menor, los entornos
en la nube todavía pueden desalinearse con una arquitectura. Por
ejemplo, desplegar servicios en distintas regiones o incluso en zonas
de disponibilidad puede disminuir o incluso anular los beneficios de
rendimiento e integridad de datos de los cachés replicados en
memoria y los cachés distribuidos. Del mismo modo, colocar
servicios, contenedores o incluso Pods de Kubernetes en la misma
máquina virtual aumentará significativamente el rendimiento, pero
también impactará negativamente en la escalabilidad, la tolerancia a
fallos, la disponibilidad y la elasticidad.

Alinear la arquitectura con la infraestructura implica una
comunicación y colaboración estrecha entre los arquitectos y los
miembros del equipo de infraestructura, o incluso adoptar prácticas
de DevOps, para que todos los interesados entiendan las
preocupaciones operativas críticas. Solo entonces los arquitectos
podrán materializar verdaderamente los beneficios operativos de la
arquitectura que seleccionaron: aquellos que nos llevaron a otorgar
esas maravillosas calificaciones de cinco estrellas.

861Arquitectura y topologías de datos

La intersección entre la arquitectura y las topologías de datos suele
pasarse por alto. Elegir el tipo o la topología de base de datos
incorrectos puede perjudicar una arquitectura y anular sus mejores
características arquitectónicas. Por ejemplo, las bases de datos
monolíticas, aunque proporcionan una buena consistencia de datos y
soporte transaccional, pueden restar escalabilidad y tolerancia a
fallos. Del mismo modo, las topologías de bases de datos
distribuidas, aunque son buenas en escalabilidad y control de
cambios, pueden disminuir la integridad de los datos, la consistencia
de los datos y el rendimiento del sistema.

Las siguientes secciones describen la intersección entre la
arquitectura y las topologías de datos.

Topología de base de datos

La topología de una base de datos, como discutimos en el Capítulo
15, se refiere a cómo se configuran sus bases de datos físicas dentro
de la arquitectura. Las tres topologías básicas incluyen una base de
datos monolítica, bases de datos distribuidas basadas en dominios o
la topología distribuida de base de datos por servicio. La Figura 26-4
ilustra estos tipos básicos de topología de base de datos.

862Este diagrama ilustra tres tipos comunes de topologías de bases de datos dentro

de  una  arquitectura  de  software,  separadas  por  líneas  punteadas.  En  la  parte

superior de cada esquema se encuentra la interfaz de usuario, la cual se comunica

con  diversos  bloques  que  representan  los  componentes  del  sistema.  El  primer

modelo  muestra  una  topología  monolítica  donde  todos  los  componentes

comparten  una  única  base  de  datos  central.  El  segundo  esquema  presenta  una

863configuración de bases de datos distribuidas por dominio, donde ciertos grupos de

componentes  utilizan  bases  de  datos  distintas.  El  tercer  modelo  representa  la

topología de base de datos por servicio, en la cual cada unidad de componentes

posee  su  propia  base  de  datos  independiente  para  garantizar  un  contexto

delimitado y mayor autonomía. (Accesibilidad de la imagen)

Figura 26-4. Tipos comunes de topologías de bases de datos

La topología de la base de datos debe estar alineada con la
arquitectura para que funcione correctamente. Por ejemplo, las
arquitecturas de microservicios suelen utilizar un patrón de base de
datos por servicio para mantener un contexto delimitado estricto. Sin
esta alineación adecuada, sería extremadamente difícil para los
arquitectos controlar los cambios, y las características operativas del
sistema, como la tolerancia a fallos, la escalabilidad, la elasticidad, la
mantenibilidad, la testeabilidad y la desplegabilidad, se verían
afectadas. Dicho esto, algunos estilos, como la arquitectura basada
en servicios (ver el Capítulo 14), son más flexibles con respecto a la
topología física de la base de datos.

Características arquitectónicas

En la Parte II de este libro, mostramos que cada estilo arquitectónico
tiene sus superpoderes (calificados con 4 o 5 estrellas) y sus
debilidades (1 o 2 estrellas). Lo mismo ocurre con los tipos de bases
de datos, y es importante alinear los superpoderes arquitectónicos
de un sistema con los superpoderes correspondientes de su tipo de
base de datos. En nuestro libro Software Architecture: The Hard
Parts, nosotros, tus autores, calificamos las características de seis
tipos diferentes de bases de datos: relacionales, clave-valor, de
documentos, columnares, de grafos y NoSQL. Quizás recuerdes que
la escalabilidad y la elasticidad son superpoderes para las
arquitecturas de microservicios, las impulsadas por eventos y las
basadas en el espacio. También son superpoderes para las bases de
datos de clave-valor y columnares, lo que significa que estos tipos

864de bases de datos son buenas opciones para amplificar esas
características arquitectónicas.

Estructura de datos

La estructura de los datos que se almacenan y a los que se accede
también es un factor en esta intersección. Si la estructura de datos
es relacional —es decir, construida sobre una jerarquía de relaciones
interdependientes—, entonces una base de datos relacional se
alineará bien. Sin embargo, almacenar pares clave-valor en una base
de datos relacional es una desalineación que puede llevar a
ineficiencias tanto en la base de datos como en la arquitectura. No
todos los datos conllevan la misma estructura, así que presta
atención a esto. Algunos datos pueden ser relacionales, otros
pueden estar basados en documentos (particularmente cuando se
almacenan cargas útiles de eventos o peticiones basadas en JSON),
y otros pueden estar impulsados por clave-valor. Dada la diversidad
potencial de las estructuras de datos dentro de cualquier
arquitectura determinada, recomendamos aprovechar las bases de
datos políglotas siempre que sea factible.

Prioridad de lectura/escritura

Si el problema de negocio involucra altos volúmenes de lectura o
escritura, esa es información importante para alinear la topología de
la base de datos con la arquitectura. Por ejemplo, si la arquitectura
requiere altos volúmenes de escritura como prioridad sobre lecturas
poco frecuentes, entonces una base de datos columnar sería una
buena opción. Sin embargo, si lo contrario es cierto y los altos
volúmenes de lectura son la prioridad, entonces una base de datos
de clave-valor, una de documentos o una de grafos sería más
apropiada. Si el sistema prioriza las lecturas y escrituras por igual,
entonces las bases de datos relacionales y NewSQL serían buenas

865opciones. Desalinear este factor puede llevar a sistemas con un
rendimiento deficiente.

Arquitectura y prácticas de ingeniería

A finales del siglo XX, se popularizaron docenas de metodologías de
desarrollo de software, incluyendo Waterfall (cascada) y muchos
tipos de Agile (como Scrum, Extreme Programming, Lean y Crystal).
En aquel entonces, la mayoría de los arquitectos creían que nada de
esto afectaba a la arquitectura de software, tratando el desarrollo
como un proceso totalmente independiente. Sin embargo, en los
últimos años, los avances en ingeniería han impuesto las
preocupaciones del proceso sobre la arquitectura de software. Es útil
separar los procesos de desarrollo de software de las prácticas de
ingeniería. Por procesos, nos referimos a cómo se forman y
gestionan los equipos, cómo se conducen las reuniones y cómo se
organizan los flujos de trabajo; en resumen, la mecánica de cómo
las personas se organizan e interactúan. Las prácticas de ingeniería,
por otro lado, se refieren a las técnicas y herramientas
independientes del proceso que los equipos utilizan para desarrollar
y lanzar software. Por ejemplo, Extreme Programming (XP),
integración continua (CI), entrega continua (CD) y desarrollo guiado
por pruebas (TDD) son todas prácticas de ingeniería probadas que
no dependen de un proceso en particular. Así, el término ingeniería
de software abarca tanto el desarrollo de software como estas
prácticas.

Centrarse en las prácticas de ingeniería es importante. El desarrollo
de software carece de muchas de las características de las disciplinas
de ingeniería más maduras. Por ejemplo, los ingenieros civiles
pueden predecir cambios estructurales con mucha más precisión de
lo que los ingenieros de software pueden predecir aspectos similares
de la estructura del software. Esto significa que el talón de Aquiles
del desarrollo de software es la estimación: ¿cuánto tiempo?,

866¿cuántos recursos?, ¿cuánto dinero? Parte de lo que contribuye a
esta dificultad es que las prácticas tradicionales de estimación no se
ajustan a la naturaleza exploratoria del desarrollo de software ni a
las incógnitas que suelen surgir al desarrollarlo.

Aunque el proceso es mayormente independiente de la arquitectura,
los procesos iterativos se adaptan mejor a su naturaleza. Intentar
construir un sistema moderno como los microservicios utilizando un
proceso anticuado como Waterfall generará mucha fricción. Un
aspecto de la arquitectura donde las metodologías Agile realmente
brillan es en la migración de un estilo arquitectónico a otro. Las
metodologías Agile soportan tales cambios mejor que los procesos
con mucha planificación porque tienen ciclos de retroalimentación
cortos y fomentan técnicas como el Patrón Strangler (estrangulador)
y los feature toggles (conmutadores de funciones).

Los arquitectos a menudo también actúan como líderes técnicos del
proyecto, lo que significa determinar qué prácticas de ingeniería
utiliza el equipo. Al igual que se considera cuidadosamente el
dominio del problema antes de elegir una arquitectura, los
arquitectos también deben asegurarse de que su estilo
arquitectónico y sus prácticas de ingeniería engranen. Por ejemplo,
la filosofía arquitectónica de los microservicios asume que los
equipos automatizarán cosas como el aprovisionamiento de
máquinas, las pruebas y el despliegue. Intentar construir una
arquitectura de microservicios con un grupo de operaciones
anticuado, procesos manuales y pocas pruebas probablemente
llevaría al fracaso. Así como diferentes dominios de problemas se
prestan a ciertos estilos arquitectónicos, también lo hacen las
diferentes prácticas de ingeniería.

La evolución del pensamiento continúa, desde Extreme Programming
hasta la entrega continua y más allá, a medida que los avances en
las prácticas de ingeniería hacen posible nuevas capacidades
arquitectónicas. El libro de Neal, Building Evolutionary Architectures
(Construyendo arquitecturas evolutivas), destaca nuevas formas de

867pensar sobre la intersección de las prácticas de ingeniería y la
arquitectura que pueden mejorar cómo automatizamos el gobierno
arquitectónico. El libro ofrece una nueva nomenclatura y forma de
pensar importante sobre las características arquitectónicas, y cubre
técnicas para construir arquitecturas que cambian con elegancia a lo
largo del tiempo.

En el mundo del desarrollo de software, nada permanece estático.
Los arquitectos pueden diseñar un sistema para que cumpla con
ciertos criterios, pero para asegurar que sus diseños sobrevivan
tanto a la implementación como al inevitable paso del cambio, lo que
necesitamos es una arquitectura evolutiva.

Building Evolutionary Architectures introduce el concepto de utilizar
funciones de aptitud arquitectónica para proteger (y gobernar) las
características arquitectónicas a medida que el cambio ocurre con el
tiempo. Recuerda del Capítulo 6 que las funciones de aptitud
arquitectónica son una forma de obtener una evaluación de
integridad objetiva de alguna(s) característica(s) arquitectónica(s).
Esta evaluación puede incluir una variedad de mecanismos, como
métricas, pruebas unitarias, monitores e ingeniería del caos.

Para ver cómo se pueden utilizar las funciones de aptitud para
ayudar a alinear esta intersección, considera el problema de negocio
de necesitar un tiempo de comercialización rápido. El tiempo de
comercialización se traduce en agilidad: la capacidad del sistema
para responder rápidamente al cambio. La agilidad es una
característica arquitectónica compuesta que consiste en
mantenibilidad, testeabilidad y desplegabilidad (ver el Capítulo 6).
Estas tres características arquitectónicas están influenciadas por las
prácticas y procedimientos de ingeniería y, como tales, pueden
medirse y rastrearse a través de funciones de aptitud. Por ejemplo,
tanto las arquitecturas de microservicios como las basadas en
servicios soportan niveles altos de agilidad. Sin embargo, si las
prácticas de ingeniería que rodean estas características
arquitectónicas no están alineadas con la arquitectura, el sistema no

868cumplirá con esos objetivos y requisitos de agilidad. Las funciones
de aptitud pueden usarse para ayudar a identificar una
desalineación, lo que impulsa al arquitecto a tomar medidas para
realinear las prácticas de ingeniería con la arquitectura (o viceversa).

Arquitectura y topologías de equipo

Como hemos discutido a lo largo de la Parte II del libro, las
topologías de equipo pueden tener un impacto directo en la
arquitectura de software, y viceversa. Esta alineación es tan
importante que hemos incluido una sección sobre topologías de
equipo para cada estilo de arquitectura que presentamos en este
libro.

Una de las formas más básicas en que las topologías de equipo
pueden alinearse con la arquitectura es por el tipo de
particionamiento. Al igual que las arquitecturas, los equipos pueden
estar particionados por dominio o técnicamente. Los equipos
particionados por dominio se organizan por área de dominio y suelen
ser multidisciplinarios, con especialización en todo el equipo. Por
ejemplo, un equipo particionado por dominio en particular podría
centrarse en la parte del sistema orientada al cliente y, como tal,
sería responsable del procesamiento de extremo a extremo de la
funcionalidad relacionada con el cliente, desde la interfaz de usuario
(UI) hasta la base de datos. Los equipos particionados técnicamente,
por el contrario, se centran cada uno en una función técnica
particular de la arquitectura y suelen organizarse por categorías
técnicas: por ejemplo, los equipos de UI, los equipos de
procesamiento de backend, los equipos de servicios compartidos y
los equipos de bases de datos se alinearían muy bien con el estilo de
arquitectura por capas. Alternativamente, estos equipos podrían
estar particionados técnicamente en equipos de funciones de
negocio y equipos de sincronización de datos, lo que se alinearía
bien con el estilo arquitectónico basado en el espacio.

869Comprender cómo se organizan los equipos es vital para garantizar
el éxito del sistema. Si la topología de equipo de la organización está
desalineada con la arquitectura, los equipos tendrán dificultades
para implementar y mantener la arquitectura, la cual difícilmente
cumplirá sus objetivos de negocio.

Arquitectura e integración de sistemas

Los sistemas rara vez viven aislados. La mayoría requiere
procesamiento y datos adicionales de otros sistemas, y eso nos lleva
a la intersección de la arquitectura y la integración de sistemas.
Cuando un sistema necesita comunicarse con otro para realizar un
procesamiento adicional o recuperar datos, su arquitecto se enfrenta
a una serie de desafíos e implicaciones. Por ejemplo, ¿está
disponible el sistema al que se llama? ¿Escala y rinde al mismo nivel
que los requisitos del sistema que realiza la llamada?

Cuando los arquitectos no se centran lo suficiente en la integración
de sistemas, el acoplamiento estático y dinámico de los sistemas
suele dar lugar a arquitecturas que no pueden escalar, no son
responsivas y carecen de agilidad. Al integrarse con otros sistemas,
considera qué protocolos de comunicación utilizar, qué tipos de
contratos tener entre sistemas, si las características arquitectónicas
de los sistemas son compatibles y si la integración preserva el
cuanto arquitectónico de cada sistema.

Arquitectura y la empresa

Cada empresa tiene un conjunto de estándares y principios rectores.
Por empresa, nos referimos a la colección de todos los sistemas y
productos dentro de una compañía (o un departamento o división
dentro de la compañía). Por ejemplo, muchas compañías imponen
ciertos estándares, prácticas o procedimientos de seguridad en las
soluciones arquitectónicas, independientemente del tipo de sistema.

870Los estándares empresariales también pueden involucrar
plataformas, tecnologías, estándares de documentación y estándares
de diagramación, por nombrar algunos. Sé consciente de los
estándares y prácticas a nivel empresarial y asegúrate de que la
arquitectura esté debidamente alineada con ellos.

Hemos experimentado muchas situaciones en las que el arquitecto
ignoró las prácticas, estándares y procedimientos a nivel
empresarial. El resultado habitual ha sido que la solución
arquitectónica, por muy eficaz que fuera técnicamente, fuera
considerada una solución fallida "de un solo uso" y desechada. No
podemos enfatizar lo suficiente la importancia de alinear la
arquitectura con las prácticas empresariales para garantizar su éxito.

Arquitectura y el entorno empresarial

El entorno empresarial tiene una influencia significativa y directa en
la arquitectura de sus sistemas (y viceversa), y el entorno
empresarial nunca deja de cambiar. ¿Está la empresa sometida a
severas medidas de reducción de costes para mantenerse a flote o
se está expandiendo agresivamente? ¿Está el negocio pivotando y
reposicionándose cada trimestre para encontrar su nicho en un
mercado altamente volátil y competitivo, o se encuentra en una
posición de estabilidad? Un arquitecto de software eficaz comprende
la posición y la dirección de la empresa y alinea las arquitecturas de
los sistemas críticos para que coincidan con el entorno empresarial.

A esta alineación la llamamos isomorfismo de dominio a
arquitectura. Por ejemplo, las empresas que atraviesan medidas
extremas de reducción de costes no se alinearían bien con
microservicios o arquitecturas basadas en el espacio, que son muy
costosas de crear y mantener. Por el contrario, las empresas que se
están expandiendo agresivamente a través de fusiones y
adquisiciones no se verían bien servidas por estilos de arquitectura
monolíticos que carecen de la capacidad de evolucionar y adaptarse.

871Un problema que los arquitectos suelen enfrentar en esta
intersección es el cambio de negocio, particularmente el cambio
desconocido. El exsecretario de Defensa de los EE. UU., Donald
Rumsfeld, dijo una vez la famosa frase:

Hay conocimientos conocidos; hay cosas que sabemos que
sabemos. También sabemos que hay incógnitas conocidas; es
decir, sabemos que hay algunas cosas que no sabemos. Pero
también hay incógnitas desconocidas: aquellas que no sabemos
que no sabemos.

Muchos productos y sistemas comienzan con una lista de incógnitas
conocidas: cosas que los desarrolladores deben aprender sobre el
dominio y la tecnología que saben que cambiarán. Sin embargo,
estos mismos sistemas también son víctimas de las incógnitas
desconocidas: cosas que nadie sabía que iban a surgir, pero que han
aparecido inesperadamente. Las "incógnitas desconocidas" son las
némesis de los sistemas de software. Esta es la razón por la que
todos los esfuerzos de software de "Gran Diseño Por Adelantado"
sufren: los arquitectos no pueden diseñar para incógnitas
desconocidas. Para citar a Mark:

Todas las arquitecturas se vuelven iterativas debido a las
incógnitas desconocidas. Agile simplemente reconoce esto y lo
hace antes.

Planificar el cambio en la arquitectura de software es difícil. Las
prácticas de arquitectura evolutiva ayudan a abordar un panorama
empresarial en constante cambio, al igual que la arquitectura
iterativa. Adoptar características arquitectónicas como la
portabilidad, escalabilidad, evolucionabilidad y adaptabilidad también
ayuda a que una arquitectura de software sea más flexible y
adaptable al cambio.

Barry O’Reilly, un experimentado arquitecto de software
especializado en la teoría de la complejidad y el diseño de software,
ideó una nueva forma de pensar sobre el cambio empresarial

872constante, llamada teoría de la residualidad. En su libro Residues:
Time, Change, and Uncertainty in Software Architecture (Leanpub,
2024), O’Reilly describe técnicas para tratar el cambio empresarial
como estresores, y los cambios arquitectónicos correspondientes
como residuos. Su teoría es que, a medida que el arquitecto
responde al cambio aplicando más y más residuos a la arquitectura,
estos residuos eventualmente comenzarán a abordar cambios
desconocidos que el arquitecto no puede predecir de ninguna
manera, creando una arquitectura que ha alcanzado un estado
crítico dentro de la teoría de la complejidad. Es una teoría
interesante, una que estamos siguiendo de cerca.

Arquitectura e IA generativa

Mientras escribimos la segunda edición de este libro a principios de
2025, la inteligencia artificial generativa (IA generativa) y los
modelos de lenguaje extensos (LLM) se han infiltrado en el mundo
del desarrollo y el diseño de software. Muchas empresas los están
incorporando a sus sistemas para realizar tareas que anteriormente
solo eran realizadas manualmente por humanos. Como es de
esperar, la IA generativa también se cruza con la arquitectura de
software: los arquitectos están incorporando LLM en las
arquitecturas de software y algunos incluso están utilizando
herramientas de IA generativa para que les ayuden a reflexionar
sobre problemas difíciles.

Incorporación de la IA generativa en la
arquitectura

Un enfoque que recomendamos para incorporar la IA generativa en
una arquitectura es aprovechar la abstracción y la modularidad. Es
importante poder reemplazar un LLM por otro rápidamente, y
permitir salvaguardas (rails) y evaluar resultados (evals) de varios
LLM.

873Por ejemplo, supongamos que una empresa de búsqueda de empleo
quiere aprovechar la IA generativa para anonimizar currículums, con
el objetivo de reducir el sesgo y centrarse en las habilidades de
quienes buscan empleo en lugar de sus datos demográficos u otros
factores similares. Esta tarea normalmente la realizan humanos,
pero podría ser realizada fácilmente por un LLM. Pero, ¿son precisos
los resultados del LLM? ¿Elimina demasiada información del
currículum? ¿Mantiene demasiada información demográfica? Para
este tipo de sistema, es vital poder recopilar muestras y métricas y
comparar motores de LLM. Herramientas como Langfuse ayudan a
crear este tipo de observabilidad dentro de la arquitectura.

La IA generativa como asistente del arquitecto

Con un prompt adecuado, un LLM (como Copilot) puede producir
código fuente que ahorra a los desarrolladores mucho tiempo y
esfuerzo. Son excelentes para resolver problemas deterministas muy
específicos, como "escribe código fuente en el lenguaje de
programación C# que genere un número PIN único de cuatro dígitos
que no tenga dígitos repetidos". Pero, ¿puede la tecnología LLM
ayudar a los arquitectos de software con sus tareas típicas? Aquí
tienes algunos ejemplos generales de prompts relacionados con la
arquitectura:

Evaluación de riesgos: "¿Existen áreas de riesgo dentro de
esta arquitectura?"

Mitigación de riesgos: "¿Cómo debería abordar este riesgo?"

Antipatrones: "¿Hay algún antipatrón común en esta
arquitectura?"

Decisiones: "¿Debería usar orquestación o coreografía para
este flujo de trabajo?"

874En el momento de escribir esta segunda edición (principios de
2025), no hemos tenido un éxito tremendo con este empeño.
Preguntar a un LLM si los microservicios o la arquitectura basada en
el espacio serían más apropiados para una situación dada rara vez
(si es que alguna vez) arroja la respuesta correcta. ¿Por qué?
Porque, como hemos demostrado en este libro, todo en la
arquitectura de software es una compensación (trade-off). Los LLM
son excelentes para comprender el conocimiento, pero hasta el día
de hoy, todavía carecen de la sabiduría necesaria para tomar
decisiones apropiadas. Esa sabiduría incluye tanto contexto que es
mucho más rápido para el arquitecto resolver un problema de
negocio por sí mismo que enseñar a un LLM todo sobre el problema
y su entorno y contexto extendidos. El hecho de que hayamos
incluido otras ocho intersecciones de las que preocuparse debería
ser prueba suficiente de que se trata de una tarea desalentadora.

Dicho esto, hemos visto algunas herramientas prometedoras. Por
ejemplo, Thoughtworks Haiven puede interpretar un diagrama de
arquitectura y describir completamente una arquitectura de
software, ahorrando el trabajo de tener que exportar un diagrama a
un formato legible por máquina como XML y usarlo para hacer el
prompt al LLM. Una vez que han importado esa información, los
usuarios pueden hacerle preguntas sencillas a Haiven sobre la
arquitectura, como si puede identificar algún cuello de botella o
problema. Otros esfuerzos han incluido el uso de un LLM para
traducir un diagrama de PlantUML o una descripción de una
arquitectura en un pseudolenguaje a código ArchUnit ejecutable
para gobernar la estructura de un sistema. Está habiendo mucha
actividad en esta área, así que espera cambios rápidos en los
próximos años sobre cómo la IA generativa puede asistir a los
arquitectos.

875Resumen

La arquitectura de software es una actividad holística que involucra
muchas facetas de una organización. Los arquitectos de software
eficaces se dan cuenta de que crear y mantener una arquitectura es
mucho más que solo seleccionar un estilo arquitectónico particular y
avanzar con la implementación. También se trata de asegurarse de
que la arquitectura esté alineada con otros aspectos del entorno, y
de usar las habilidades de comunicación y colaboración descritas en
la Parte III para lograr que esa alineación ocurra.
