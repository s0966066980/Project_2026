# Separate Admin and Kiosk Product Frontends

Status: accepted

Admin and Kiosk are independently built and tested browser applications that own separate UI/UX, bootstrap, state, features, styles, and test suites, and neither application may import the other or switch identity through a runtime mode. They may share only a stateless frontend foundation containing generated capability clients, design tokens, primitives, and transports. This prevents one product's interface changes from interfering with the other without duplicating low-level contracts and accessibility foundations.
