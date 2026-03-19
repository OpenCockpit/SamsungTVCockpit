DESCRIPTION = "SamsungTV plugin for enigma2"
MAINTAINER = "xcentaurix"
LICENSE = "GPL-3.0-only"
LIC_FILES_CHKSUM = "file://LICENSE;md5=1ebbd3e34237af26da5dc08a4e440464"
HOMEPAGE = "https://github.com/OpenCockpit/SamsungTV"

RDEPENDS:${PN} = "python3-multiprocessing python3-requests python3-zoneinfo"

inherit gitpkgv allarch python3native gettext

PV = "1.0+git"
MAINTAINER = "OpenViX"
PKGV = "1.0+git${GITPKGV}"
SRCREV = "${AUTOREV}"
SRC_URI = "git://github.com/OpenCockpit/SamsungTV.git;protocol=https;branch=master"
HOMEPAGE = "https://github.com/OpenCockpit/SamsungTV"

pluginpath = "/usr/lib/enigma2/python/Plugins/Extensions/SamsungTV"
configpath = "/etc/enigma2"

do_install:append() {
	install -d ${D}${configpath}
	cp -r ${S}/src/skin/* ${D}${configpath}/
	rm -rf ${S}/src/skin
	install -d ${D}${pluginpath}
	cp -r ${S}/src/* ${D}${pluginpath}/
	python3 -m compileall -o2 -b ${D} -d /
	if [ -f /usr/bin/msgfmt ] ; then
		find ${S}/po/ -maxdepth 1 -type f -name '*.po' | while read po ; do
			## remove everything before and including the "/"
			filename=${po##*/}
			## remove everything after and including the "."
			cc=${filename%%.*}
			folder=${D}${pluginpath}/locale/${cc}/LC_MESSAGES
			mkdir -p ${folder}
			/usr/bin/msgfmt -o ${folder}/m3uiptv.mo ${po}
		done
	fi
}

FILES:${PN} = "${configpath}/ ${pluginpath}/"

FILES:${PN}-src = "${pluginpath}/*.py"
