#!groovy

@Library('pipelib')
import org.veupathdb.lib.Builder

node('podbuild') {
  def builder = new Builder(this)

  builder.gitClone()
  builder.buildContainers([
    [ name: 'strategist-api', dockerfile: 'apps/api/Dockerfile' ],
    [ name: 'strategist-web', dockerfile: 'apps/web/Dockerfile',
      buildArgs: [ NEXT_PUBLIC_API_URL: 'http://strategist-api:8000' ] ]
  ])
}
