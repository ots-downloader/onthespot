# Copyright 2024-2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

EAPI=8

DISTUTILS_USE_PEP517=setuptools
PYTHON_COMPAT=( python3_{10..13} )

inherit distutils-r1 desktop xdg

if [[ ${PV} == *9999 ]]; then
	inherit git-r3
	EGIT_REPO_URI="https://github.com/ots-downloader/onthespot.git"
else
	SRC_URI="https://github.com/ots-downloader/onthespot/archive/refs/tags/v${PV}.tar.gz
			 -> ${P}.tar.gz"
	KEYWORDS="~amd64"
fi

DESCRIPTION="qt based music downloader written in python"
HOMEPAGE="https://github.com/ots-downloader/onthespot"

LICENSE="GPL-2"
SLOT="0"
IUSE="webui"

BDEPEND="
	dev-python/packaging
"

RDEPEND="
	dev-python/flask
	dev-python/flask-login
	dev-python/librespot
	dev-python/m3u8
	dev-python/music-tag
	dev-python/pillow
	dev-python/protobuf
	dev-python/pyqt6[network,widgets]
	dev-python/pywidevine
	dev-python/requests
	dev-python/urllib3
	media-libs/mutagen
	media-video/ffmpeg[lame,openssl,sdl]
	net-misc/yt-dlp
	webui? (
		acct-group/onthespot
		acct-user/onthespot
	)
"

src_install() {
	distutils-r1_src_install

	if use webui ; then
		newconfd "${FILESDIR}/${PN}.confd" "${PN}"
		newinitd "${FILESDIR}/${PN}.initd" "${PN}"
	fi

	domenu "${S}"/src/onthespot/resources/org.onthespot.OnTheSpot.desktop
	newicon -s 256 "${S}"/src/onthespot/resources/icons/onthespot.png onthespot.png
}
